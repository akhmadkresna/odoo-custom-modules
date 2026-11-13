from datetime import timedelta

from odoo import api, fields, models

from .oauth_client import generate_token, hash_token

ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)


class McpOAuthToken(models.Model):
    _name = "mcp.oauth.token"
    _description = "MCP OAuth Token"
    _order = "create_date desc"

    client_id = fields.Many2one("mcp.oauth.client", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    code_id = fields.Many2one("mcp.oauth.code", ondelete="set null")
    access_hash = fields.Char(index=True)
    refresh_hash = fields.Char(index=True)
    scope = fields.Char()
    expires_at = fields.Datetime()
    refresh_expires_at = fields.Datetime()
    revoked = fields.Boolean(index=True)
    last_used_at = fields.Datetime(readonly=True)
    last_used_ip = fields.Char(readonly=True)

    @api.model
    def issue(self, client, user, scope=None, code=None):
        access, refresh = generate_token(), generate_token()
        now = fields.Datetime.now()
        rec = self.sudo().create({
            "client_id": client.id, "user_id": user.id, "scope": scope,
            "code_id": code.id if code else False,
            "access_hash": hash_token(access), "refresh_hash": hash_token(refresh),
            "expires_at": now + ACCESS_TTL, "refresh_expires_at": now + REFRESH_TTL,
        })
        return rec, access, refresh

    def refresh(self):
        """Rotate both tokens (the old refresh token stops working)."""
        self.ensure_one()
        access, refresh = generate_token(), generate_token()
        now = fields.Datetime.now()
        self.sudo().write({
            "access_hash": hash_token(access), "refresh_hash": hash_token(refresh),
            "expires_at": now + ACCESS_TTL, "refresh_expires_at": now + REFRESH_TTL,
        })
        return access, refresh

    @api.model
    def resolve_access(self, token, ip=None):
        rec = self.sudo().search([("access_hash", "=", hash_token(token)), ("revoked", "=", False)], limit=1)
        now = fields.Datetime.now()
        if not rec or rec.expires_at < now or not rec.user_id.active:
            return self.browse()
        if not (rec.client_id.active and rec.client_id.approved):
            return self.browse()
        rec.write({"last_used_at": now, "last_used_ip": ip})
        return rec

    @api.model
    def resolve_refresh(self, token):
        rec = self.sudo().search([("refresh_hash", "=", hash_token(token)), ("revoked", "=", False)], limit=1)
        if not rec or not rec.refresh_expires_at or rec.refresh_expires_at < fields.Datetime.now():
            return self.browse()
        return rec

    def action_revoke(self):
        self.write({"revoked": True})

    @api.autovacuum
    def _gc_tokens(self):
        limit = fields.Datetime.now() - timedelta(days=1)
        self.sudo().search(["|", ("revoked", "=", True), ("refresh_expires_at", "<", limit)]).unlink()
