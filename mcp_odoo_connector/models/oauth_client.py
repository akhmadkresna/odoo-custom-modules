import base64
import hashlib
import secrets
import urllib.parse

from odoo import api, fields, models

# Redirect URIs of the official connector platforms. Clients registering with
# one of these are auto-approved (the user still has to log in and consent).
TRUSTED_REDIRECT_URIS = {
    "https://chatgpt.com/connector_platform_oauth_redirect",
    "https://platform.openai.com/apps-manage/oauth",
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
}


def generate_token():
    return secrets.token_urlsafe(32)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_pkce(verifier, challenge):
    """S256 only."""
    if not verifier or not challenge:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", "ignore")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(computed, challenge)


class McpOAuthClient(models.Model):
    _name = "mcp.oauth.client"
    _description = "MCP OAuth Client"
    _order = "create_date desc"

    name = fields.Char(required=True)
    client_id = fields.Char(required=True, index=True, copy=False, default=lambda s: generate_token())
    client_secret_hash = fields.Char(copy=False)
    redirect_uris = fields.Text(required=True, help="One redirect URI per line.")
    token_endpoint_auth_method = fields.Selection(
        [("none", "Public (PKCE only)"), ("client_secret_post", "Client secret")],
        default="none", required=True,
    )
    active = fields.Boolean(default=True)
    approved = fields.Boolean(help="Clients must be approved before they can authorize users.")
    allow_write = fields.Boolean(
        help="Let this client create and update records (as the signed-in user). "
             "Off = read-only. Deleting is never allowed over OAuth.",
    )
    created_via_dcr = fields.Boolean("Dynamic registration", readonly=True)
    token_ids = fields.One2many("mcp.oauth.token", "client_id")

    def get_redirect_uris(self):
        self.ensure_one()
        return [l.strip() for l in (self.redirect_uris or "").splitlines() if l.strip()]

    def is_redirect_allowed(self, uri):
        """Exact match only (OAuth 2.1)."""
        self.ensure_one()
        return bool(uri) and uri in self.get_redirect_uris()

    def check_secret(self, secret):
        self.ensure_one()
        if self.token_endpoint_auth_method == "none":
            return True
        return bool(secret and self.client_secret_hash and secrets.compare_digest(
            hash_token(secret), self.client_secret_hash))

    def action_approve(self):
        self.write({"approved": True})

    @api.model
    def register_from_dcr(self, payload):
        """RFC 7591 dynamic client registration. Returns (client, plain_secret)."""
        uris = payload.get("redirect_uris") or []
        if isinstance(uris, str):
            uris = [uris]
        uris = [u.strip() for u in uris if isinstance(u, str) and u.strip()]
        if not uris:
            raise ValueError("redirect_uris is required")
        for u in uris:
            p = urllib.parse.urlparse(u)
            local = p.hostname in ("localhost", "127.0.0.1")
            if p.scheme != "https" and not (p.scheme == "http" and local):
                raise ValueError("redirect_uris must be https (or http on localhost)")
            if p.fragment:
                raise ValueError("redirect_uris must not contain a fragment")
        method = payload.get("token_endpoint_auth_method")
        method = method if method in ("none", "client_secret_post") else "none"
        secret = generate_token() if method == "client_secret_post" else False
        name = str(payload.get("client_name") or "MCP client")[:128]
        client = self.sudo().create({
            "name": name,
            "redirect_uris": "\n".join(uris),
            "token_endpoint_auth_method": method,
            "client_secret_hash": hash_token(secret) if secret else False,
            "created_via_dcr": True,
            "approved": all(u in TRUSTED_REDIRECT_URIS for u in uris),
        })
        return client, secret
