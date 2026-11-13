from datetime import timedelta

from odoo import api, fields, models

from .oauth_client import generate_token, hash_token, verify_pkce


class McpOAuthCode(models.Model):
    _name = "mcp.oauth.code"
    _description = "MCP OAuth Authorization Code"

    client_id = fields.Many2one("mcp.oauth.client", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    code_hash = fields.Char(required=True, index=True)
    redirect_uri = fields.Char(required=True)
    code_challenge = fields.Char(required=True)
    scope = fields.Char()
    expires_at = fields.Datetime(required=True)
    used = fields.Boolean()

    @api.model
    def issue(self, client, user, redirect_uri, code_challenge, scope=None):
        code = generate_token()
        self.sudo().create({
            "client_id": client.id,
            "user_id": user.id,
            "code_hash": hash_token(code),
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "scope": scope,
            "expires_at": fields.Datetime.now() + timedelta(minutes=5),
        })
        return code

    @api.model
    def consume(self, code, client, redirect_uri, verifier):
        rec = self.sudo().search([
            ("code_hash", "=", hash_token(code)),
            ("client_id", "=", client.id),
        ], limit=1)
        if not rec or rec.used:
            if rec:  # replayed code: revoke what it produced
                self.env["mcp.oauth.token"].sudo().search([
                    ("client_id", "=", client.id), ("user_id", "=", rec.user_id.id),
                    ("code_id", "=", rec.id)]).write({"revoked": True})
            return self.browse()
        rec.used = True
        if (rec.expires_at < fields.Datetime.now()
                or rec.redirect_uri != redirect_uri
                or not verify_pkce(verifier, rec.code_challenge)):
            return self.browse()
        return rec

    @api.autovacuum
    def _gc_codes(self):
        limit = fields.Datetime.now() - timedelta(days=1)
        self.sudo().search([("expires_at", "<", limit)]).unlink()
