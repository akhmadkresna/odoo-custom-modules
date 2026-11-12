import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models


class SsPlantationFieldDevice(models.Model):
    """A phone paired with the offline field app. It holds a long-lived token (stored hashed)
    that authorises sync calls, so the app keeps working after the Odoo session has expired."""
    _name = 'ss.plantation.field.device'
    _description = 'Plantation Field Device'
    _order = 'last_sync desc, id desc'

    name = fields.Char(string="Device", required=True)
    user_id = fields.Many2one('res.users', string="User", required=True, index=True, ondelete='cascade')
    token_hash = fields.Char(readonly=True, copy=False, index=True)
    active = fields.Boolean(default=True, help="Untick to revoke this device. It can no longer sync.")
    expires_at = fields.Datetime(readonly=True, copy=False)
    last_sync = fields.Datetime(readonly=True, copy=False)
    sync_count = fields.Integer(readonly=True, copy=False)

    @api.model
    def _hash_token(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    @api.model
    def _token_days(self):
        return self.env['ir.config_parameter'].sudo().get_int('ss_plantation.field_token_days', 90)

    @api.model
    def _issue(self, user, name):
        """Create a device for `user` and return (device, raw_token). The raw token is shown once."""
        token = secrets.token_urlsafe(32)
        device = self.sudo().create({
            'name': name or self.env._("Phone"),
            'user_id': user.id,
            'token_hash': self._hash_token(token),
            'expires_at': fields.Datetime.now() + timedelta(days=self._token_days()),
        })
        return device, token

    @api.model
    def _authenticate(self, token):
        """Return the active, unexpired device for a raw token, or an empty recordset."""
        if not token:
            return self.browse()
        device = self.sudo().search([('token_hash', '=', self._hash_token(token))], limit=1)
        if not device or not device.user_id.active:
            return self.browse()
        if device.expires_at and device.expires_at < fields.Datetime.now():
            return self.browse()
        return device

    def _touch(self):
        """Record a successful sync and slide the expiry forward."""
        self.ensure_one()
        self.sudo().write({
            'last_sync': fields.Datetime.now(),
            'sync_count': self.sync_count + 1,
            'expires_at': fields.Datetime.now() + timedelta(days=self._token_days()),
        })
