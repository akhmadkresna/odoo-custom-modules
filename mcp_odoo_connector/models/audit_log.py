from datetime import timedelta

from odoo import api, fields, models


class McpAuditLog(models.Model):
    _name = "mcp.audit.log"
    _description = "MCP Audit Log"
    _order = "id desc"

    user_id = fields.Many2one("res.users", ondelete="set null", index=True)
    source = fields.Selection([("api_key", "API key"), ("oauth", "OAuth")])
    credential = fields.Char()
    tool = fields.Char(index=True)
    model_name = fields.Char()
    status = fields.Selection(
        [("ok", "OK"), ("denied", "Denied"), ("error", "Error")], index=True
    )
    message = fields.Text()
    arguments = fields.Text()
    duration_ms = fields.Integer()
    ip = fields.Char()

    @api.autovacuum
    def _gc_old_logs(self):
        days = int(self.env["ir.config_parameter"].sudo().get_param(
            "mcp_odoo_connector.audit_retention_days", "90"))
        limit = fields.Datetime.now() - timedelta(days=days)
        self.sudo().search([("create_date", "<", limit)]).unlink()
