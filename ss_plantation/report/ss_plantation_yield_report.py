from odoo import fields, models
from odoo.tools import SQL


class SsPlantationYieldReport(models.Model):
    _name = 'ss.plantation.yield.report'
    _description = 'Plantation Yield and Cost'
    _auto = False
    _order = 'month desc, block_id'
    _depends = {
        'ss.plantation.harvest.tally.line': [
            'block_id', 'tally_date', 'tally_state', 'bunches_ripe', 'bunches_overripe',
            'est_weight_kg'],
        'ss.plantation.weigh.ticket': ['date', 'state', 'direction', 'payable_kg', 'company_id'],
        'ss.plantation.transport': ['ticket_id', 'state'],
        'ss.plantation.transport.line': ['transport_id', 'block_id', 'est_weight_kg'],
        'account.analytic.line': ['account_id', 'date', 'amount'],
        'ss.plantation.block': ['analytic_account_id', 'division_id', 'estate_id', 'company_id'],
    }

    block_id = fields.Many2one('ss.plantation.block', readonly=True)
    division_id = fields.Many2one('ss.plantation.division', readonly=True)
    estate_id = fields.Many2one('ss.plantation.estate', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    month = fields.Date(readonly=True)
    bunches = fields.Integer(string="Bunches", readonly=True)
    est_weight_kg = fields.Float(string="Estimated (kg)", readonly=True)
    weighed_kg = fields.Float(string="Weighed (kg)", readonly=True)
    cost = fields.Float(string="Cost", readonly=True)

    @property
    def _table_sql(self):
        plan = self.env.ref('ss_plantation.analytic_plan_block', raise_if_not_found=False)
        if plan:
            cost_rows = SQL("""
                SELECT b2.id,
                       date_trunc('month', al.date)::date,
                       0, 0.0, 0.0, -al.amount
                  FROM account_analytic_line al
                  JOIN ss_plantation_block b2 ON b2.analytic_account_id = %s
            """, SQL.identifier('al', plan._column_name()))
        else:  # first install: the plan is created after this view; init() runs again afterwards
            cost_rows = SQL("SELECT NULL::int, NULL::date, 0, 0.0, 0.0, 0.0 WHERE FALSE")
        return SQL("""(
            SELECT row_number() OVER (
                       ORDER BY q.block_id, q.month, q.bunches, q.est_weight_kg, q.weighed_kg, q.cost
                   ) AS id,
                   q.block_id, b.division_id, b.estate_id, b.company_id, q.month,
                   q.bunches, q.est_weight_kg, q.weighed_kg, q.cost
              FROM (
                SELECT tl.block_id,
                       date_trunc('month', tl.tally_date)::date AS month,
                       tl.bunches_ripe + tl.bunches_overripe AS bunches,
                       tl.est_weight_kg AS est_weight_kg,
                       0.0 AS weighed_kg, 0.0 AS cost
                  FROM ss_plantation_harvest_tally_line tl
                 WHERE tl.tally_state = 'confirmed'
                UNION ALL
                SELECT l.block_id,
                       date_trunc('month', t.date)::date,
                       0, 0.0,
                       t.payable_kg * l.est_weight_kg
                         / NULLIF(SUM(l.est_weight_kg) OVER (PARTITION BY t.id), 0),
                       0.0
                  FROM ss_plantation_weigh_ticket t
                  JOIN ss_plantation_transport n ON n.ticket_id = t.id AND n.state != 'cancel'
                  JOIN ss_plantation_transport_line l ON l.transport_id = n.id
                 WHERE t.state = 'confirmed' AND t.direction = 'estate_in'
                UNION ALL
                %s
              ) q
              JOIN ss_plantation_block b ON b.id = q.block_id
        )""", cost_rows)
