import base64
import hashlib
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMcp(HttpCase):

    def setUp(self):
        super().setUp()
        self.user = self.env.ref("base.user_admin")
        self.key = self.env["mcp.api.key"].create({"name": "t", "user_id": self.user.id})
        res = self.key.action_generate_key()
        self.token = res["params"]["message"]
        self.key.access_ids = [(0, 0, {
            "model_id": self.env["ir.model"]._get("res.partner").id,
            "perm_read": True, "perm_create": True})]

    def _rpc(self, method, params=None, token=None, rid=1):
        headers = {"Content-Type": "application/json"}
        t = self.token if token is None else token
        if t:
            headers["Authorization"] = "Bearer " + t
        body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        return self.url_open("/mcp", data=json.dumps(body), headers=headers)

    def _call(self, name, args):
        r = self._rpc("tools/call", {"name": name, "arguments": args})
        return r.json()["result"]

    def test_auth_required(self):
        r = self._rpc("ping", token="")
        self.assertEqual(r.status_code, 401)
        self.assertIn("resource_metadata", r.headers["WWW-Authenticate"])
        self.assertEqual(self._rpc("ping", token="mcp_bad").status_code, 401)

    def test_initialize_and_list(self):
        r = self._rpc("initialize", {"protocolVersion": "2025-06-18"}).json()
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        names = {t["name"] for t in self._rpc("tools/list").json()["result"]["tools"]}
        self.assertTrue({"search", "fetch", "odoo_search_read"} <= names)

    def test_key_scopes(self):
        res = self._call("odoo_create", {"model": "res.partner", "values": {"name": "MCP Test Co"}})
        self.assertFalse(res.get("isError"), res)
        res = self._call("odoo_write", {"model": "res.partner", "ids": [1], "values": {"name": "x"}})
        self.assertTrue(res["isError"])  # no write permission
        res = self._call("odoo_search_read", {"model": "res.users", "fields": ["login"]})
        self.assertTrue(res["isError"])  # not in key scope
        res = self._call("odoo_search_read", {"model": "mcp.api.key"})
        self.assertTrue(res["isError"])  # blocked model
        self.assertTrue(self.env["mcp.audit.log"].search([("status", "=", "denied")]))

    def test_search_fetch(self):
        self.key.access_ids.perm_read = True
        res = self._call("search", {"query": "MCP Test"})
        self.env["res.partner"].create({"name": "MCP Test Co"})
        res = self._call("search", {"query": "MCP Test"})
        hits = json.loads(res["content"][0]["text"])["results"]
        self.assertTrue(hits)
        doc = json.loads(self._call("fetch", {"id": hits[0]["id"]})["content"][0]["text"])
        self.assertIn("MCP Test Co", doc["title"])

    def test_oauth_flow(self):
        base = self.base_url()
        reg = self.url_open("/oauth/register", data=json.dumps({
            "client_name": "ChatGPT",
            "redirect_uris": ["https://chatgpt.com/connector_platform_oauth_redirect"]}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(reg.status_code, 201)
        client = self.env["mcp.oauth.client"].search([("client_id", "=", reg.json()["client_id"])])
        self.assertTrue(client.approved)
        verifier = "v" * 50
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        code = self.env["mcp.oauth.code"].issue(
            client, self.user, "https://chatgpt.com/connector_platform_oauth_redirect", challenge)
        data = {"grant_type": "authorization_code", "client_id": client.client_id, "code": code,
                "redirect_uri": "https://chatgpt.com/connector_platform_oauth_redirect",
                "code_verifier": verifier}
        tok = self.url_open("/oauth/token", data=data)
        self.assertEqual(tok.status_code, 200, tok.text)
        access = tok.json()["access_token"]
        # OAuth token works and is read-only by default
        self.assertFalse(self._rpc("tools/list", token=access).json().get("error"))
        res = self._rpc("tools/call", {"name": "odoo_create", "arguments": {
            "model": "res.partner", "values": {"name": "nope"}}}, token=access).json()["result"]
        self.assertTrue(res["isError"])
        # refresh rotates
        ref = self.url_open("/oauth/token", data={"grant_type": "refresh_token", "client_id": client.client_id,
                                                  "refresh_token": tok.json()["refresh_token"]})
        self.assertEqual(ref.status_code, 200)
        self.assertEqual(self._rpc("ping", token=access).status_code, 401)  # old token rotated out
        # replaying the authorization code fails and revokes what it produced
        self.assertEqual(self.url_open("/oauth/token", data=data).status_code, 400)
        new_access = self.env["mcp.oauth.token"].search([("client_id", "=", client.id)])
        self.assertTrue(new_access.revoked)
