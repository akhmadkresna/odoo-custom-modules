import json
import urllib.parse

from odoo import http
from odoo.http import request


class McpOAuthController(http.Controller):

    def _base(self):
        return (request.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")

    def _json(self, payload, status=200):
        resp = request.make_response(json.dumps(payload), headers=[
            ("Content-Type", "application/json"), ("Cache-Control", "no-store"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Headers", "authorization, content-type"),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS")])
        resp.status_code = status
        return resp

    def _err(self, error, desc, status=400):
        return self._json({"error": error, "error_description": desc}, status)

    def _body(self):
        ctype = request.httprequest.content_type or ""
        if "application/json" in ctype:
            try:
                data = json.loads(request.httprequest.get_data(as_text=True) or "{}")
                return data if isinstance(data, dict) else {}
            except ValueError:
                return {}
        return dict(request.httprequest.form)

    # ---- discovery
    @http.route(["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"],
                type="http", auth="public", methods=["GET", "OPTIONS"], csrf=False)
    def protected_resource(self, **kw):
        return self._json({"resource": self._base() + "/mcp", "authorization_servers": [self._base()],
                           "bearer_methods_supported": ["header"]})

    @http.route(["/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"],
                type="http", auth="public", methods=["GET", "OPTIONS"], csrf=False)
    def authorization_server(self, **kw):
        b = self._base()
        return self._json({
            "issuer": b,
            "authorization_endpoint": b + "/oauth/authorize",
            "token_endpoint": b + "/oauth/token",
            "registration_endpoint": b + "/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "scopes_supported": ["mcp"],
        })

    # ---- dynamic client registration
    @http.route("/oauth/register", type="http", auth="public", methods=["POST", "OPTIONS"], csrf=False)
    def register(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._json({})
        try:
            client, secret = request.env["mcp.oauth.client"].register_from_dcr(self._body())
        except ValueError as e:
            return self._err("invalid_client_metadata", str(e))
        out = {
            "client_id": client.client_id,
            "client_id_issued_at": int(client.create_date.timestamp()),
            "client_name": client.name,
            "redirect_uris": client.get_redirect_uris(),
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": client.token_endpoint_auth_method,
        }
        if secret:
            out["client_secret"] = secret
        return self._json(out, 201)

    # ---- authorization (browser)
    def _validate(self, p):
        """Return (client, error_html_or_None). Errors before the redirect URI is trusted are shown, not redirected."""
        client = request.env["mcp.oauth.client"].sudo().search([("client_id", "=", p.get("client_id") or "")], limit=1)
        if not client or not client.active:
            return None, "Unknown OAuth client."
        if not client.is_redirect_allowed(p.get("redirect_uri")):
            return None, "Redirect URI is not registered for this client."
        if p.get("response_type", "code") != "code":
            return None, "Only response_type=code is supported."
        if not p.get("code_challenge") or p.get("code_challenge_method", "S256") != "S256":
            return None, "PKCE with code_challenge_method=S256 is required."
        return client, None

    @http.route("/oauth/authorize", type="http", auth="public", methods=["GET"], csrf=False)
    def authorize(self, **kw):
        p = dict(request.httprequest.args)
        client, error = self._validate(p)
        if error:
            return request.render("mcp_odoo_connector.oauth_error", {"message": error}, status=400)
        if not client.approved:
            return request.render("mcp_odoo_connector.oauth_error", {
                "message": "This client (%s) is waiting for administrator approval in Odoo (MCP > OAuth Clients)."
                           % client.name}, status=403)
        if not request.session.uid:
            back = "/oauth/authorize?" + urllib.parse.urlencode(p)
            return request.redirect("/web/login?redirect=" + urllib.parse.quote(back, safe=""))
        return request.render("mcp_odoo_connector.oauth_consent", {
            "client": client, "user": request.env.user, "p": p, "writes": client.allow_write})

    @http.route("/oauth/authorize/decision", type="http", auth="user", methods=["POST"], csrf=True)
    def decision(self, **kw):
        p = dict(request.httprequest.form)
        client, error = self._validate(p)
        if error or not client.approved:
            return request.render("mcp_odoo_connector.oauth_error", {"message": error or "Client not approved."}, status=400)
        query = {}
        if p.get("state"):
            query["state"] = p["state"]
        if p.get("decision") != "allow":
            query.update(error="access_denied")
        else:
            query["code"] = request.env["mcp.oauth.code"].issue(
                client, request.env.user, p["redirect_uri"], p["code_challenge"], p.get("scope"))
        sep = "&" if "?" in p["redirect_uri"] else "?"
        return request.redirect(p["redirect_uri"] + sep + urllib.parse.urlencode(query), local=False)

    # ---- token
    @http.route("/oauth/token", type="http", auth="public", methods=["POST", "OPTIONS"], csrf=False)
    def token(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return self._json({})
        d = self._body()
        auth = request.httprequest.authorization
        client_id = d.get("client_id") or (auth.username if auth else None)
        secret = d.get("client_secret") or (auth.password if auth else None)
        client = request.env["mcp.oauth.client"].sudo().search([("client_id", "=", client_id or "")], limit=1)
        if not client or not client.active or not client.approved or not client.check_secret(secret):
            return self._err("invalid_client", "Unknown, unapproved or unauthenticated client", 401)

        Token = request.env["mcp.oauth.token"]
        grant = d.get("grant_type")
        if grant == "authorization_code":
            code = request.env["mcp.oauth.code"].consume(
                d.get("code") or "", client, d.get("redirect_uri"), d.get("code_verifier"))
            if not code:
                return self._err("invalid_grant", "Invalid, expired or already used authorization code")
            _rec, access, refresh = Token.issue(client, code.user_id, code.scope, code)
        elif grant == "refresh_token":
            rec = Token.resolve_refresh(d.get("refresh_token") or "")
            if not rec or rec.client_id != client:
                return self._err("invalid_grant", "Invalid refresh token")
            access, refresh = rec.refresh()
        else:
            return self._err("unsupported_grant_type", "Use authorization_code or refresh_token")
        return self._json({"access_token": access, "token_type": "Bearer", "expires_in": 3600,
                           "refresh_token": refresh, "scope": "mcp"})
