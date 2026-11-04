from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestAccess(SsPlantationCommon):

    def _clerk(self, login):
        return self.env['res.users'].sudo().create({
            'name': login, 'login': login,
            'group_ids': [Command.set([self.env.ref('ss_plantation.group_plantation_user').id])],
        })

    def test_company_isolation(self):
        other = self.env['res.company'].sudo().create({'name': 'Other Estate Co'})
        foreign = self.env['ss.plantation.estate'].sudo().create({
            'name': 'Foreign', 'company_id': other.id})
        env = self.env['ss.plantation.estate'].with_context(allowed_company_ids=[self.company.id])
        self.assertFalse(env.search([('id', '=', foreign.id)]))
        self.assertTrue(env.search([('id', '=', self.estate.id)]))

    def test_clerk_cannot_edit_master_data(self):
        clerk = self._clerk('clerk2_ss')
        with self.assertRaises(AccessError):
            self.block.with_user(clerk).write({'name': 'Renamed'})
        self.assertTrue(self.block.with_user(clerk).read(['name']))

    def test_clerk_cannot_read_pay(self):
        clerk = self._clerk('clerk3_ss')
        with self.assertRaises(AccessError):
            self.env['ss.plantation.pay.scheme'].with_user(clerk).search([])
