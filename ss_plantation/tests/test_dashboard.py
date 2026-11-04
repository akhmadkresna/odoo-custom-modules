import json

from odoo.tests import tagged

from .common import SsPlantationCommon


@tagged('post_install', '-at_install')
class TestDashboards(SsPlantationCommon):

    def _field_exists(self, model_name, path):
        """True when the first hop of `path` is a stored or computed field of the model."""
        model = self.env[model_name]
        head = path.split('.')[0]
        return head == '__count' or head in model._fields

    def test_dashboard_definitions_are_valid(self):
        group = self.env.ref('ss_plantation.spreadsheet_dashboard_group_plantation')
        dashboards = self.env['spreadsheet.dashboard'].sudo().search(
            [('dashboard_group_id', '=', group.id)])
        self.assertEqual(len(dashboards), 4)
        for dashboard in dashboards:
            data = json.loads(bytes(dashboard.spreadsheet_binary_data))
            self.assertTrue(data['sheets'])
            for pivot in data['pivots'].values():
                self.assertIn(pivot['model'], self.env, dashboard.name)
                for measure in pivot['measures']:
                    self.assertTrue(
                        self._field_exists(pivot['model'], measure['fieldName']),
                        f"{dashboard.name}: {pivot['model']}.{measure['fieldName']}")
                for row in pivot['rows']:
                    self.assertTrue(
                        self._field_exists(pivot['model'], row['fieldName']),
                        f"{dashboard.name}: {pivot['model']}.{row['fieldName']}")
                for match in pivot['fieldMatching'].values():
                    self.assertTrue(
                        self._field_exists(pivot['model'], match['chain']),
                        f"{dashboard.name}: {pivot['model']}.{match['chain']}")
            for spreadsheet_list in data['lists'].values():
                for column in spreadsheet_list['columns']:
                    self.assertTrue(self._field_exists(spreadsheet_list['model'], column['name']))
