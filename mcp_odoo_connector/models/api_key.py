import hashlib
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class McpApiKey(models.Model):
    _name = "mcp.api.key"
    _description = "MCP API Key"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one(
        "res.users", string="Acts as user", required=True,
        default=lambda self: self.env.user, ondelete="cascade",
        help="Calls made with this key run with this user's Odoo access rights.",
    )
    key_prefix = fields.Char(readonly=True, copy=False)
    key_hash = fields.Char(readonly=True, copy=False, index=True)
    expires_at = fields.Datetime()
    last_used_at = fields.Datetime(readonly=True)
    last_used_ip = fields.Char(readonly=True)
    access_ids = fields.One2many("mcp.api.key.access", "key_id", string="Model access")

    def action_generate_key(self):
        """(Re)generate the secret. It is shown once and only its hash is stored."""
        self.ensure_one()
        token = "mcp_" + secrets.token_urlsafe(32)
        self.write({"key_hash": hash_token(token), "key_prefix": token[:8]})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Copy this key now - it will not be shown again"),
                "message": token,
                "type": "warning",
                "sticky": True,
            },
        }

    @api.model
    def resolve(self, token, ip=None):
        if not token or not token.startswith("mcp_"):
            return self.browse()
        key = self.sudo().search([("key_hash", "=", hash_token(token))], limit=1)
        if not key or not key.user_id.active:
            return self.browse()
        if key.expires_at and key.expires_at < fields.Datetime.now():
            return self.browse()
        key.write({"last_used_at": fields.Datetime.now(), "last_used_ip": ip})
        return key


class McpApiKeyAccess(models.Model):
    _name = "mcp.api.key.access"
    _description = "MCP API Key Model Access"
    _order = "model_name"

    key_id = fields.Many2one("mcp.api.key", required=True, ondelete="cascade")
    model_id = fields.Many2one(
        "ir.model", required=True, ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model_name = fields.Char("Technical name", related="model_id.model", store=True, index=True)
    perm_read = fields.Boolean("Read", default=True)
    perm_create = fields.Boolean("Create")
    perm_write = fields.Boolean("Write")
    perm_unlink = fields.Boolean("Delete")

    _sql_constraints = [
        ("key_model_uniq", "unique(key_id, model_id)", "One line per model and key."),
    ]
