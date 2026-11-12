from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class SsPlantationPayScheme(models.Model):
    _name = 'ss.plantation.pay.scheme'
    _description = 'Plantation Harvest Pay Scheme'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    mode = fields.Selection(
        [('daily', "Daily wage (penalties only)"),
         ('piece_rate', "Piece rate (per kg)"),
         ('mixed', "Daily basis plus bonus above it")],
        required=True, default='mixed',
        help="Daily wage itself stays in the normal payroll contract. This scheme only "
             "adds the harvest bonus, or the piece-rate pay, minus penalties.")
    rate_per_kg = fields.Monetary(
        string="Piece Rate / kg", currency_field='currency_id',
        help="Piece rate mode: paid on every harvested kg.")
    basis_kg = fields.Float(
        string="Daily Basis (kg)", digits=(16, 1),
        help="Mixed mode: kilograms a harvester must reach per day before the bonus starts.")
    bonus_per_kg = fields.Monetary(
        string="Bonus / kg above Basis", currency_field='currency_id')
    penalty_unripe = fields.Monetary(
        string="Penalty / Unripe Bunch", currency_field='currency_id')
    penalty_loose_left = fields.Monetary(
        string="Penalty / kg Loose Fruit Left", currency_field='currency_id')
    tier_ids = fields.One2many(
        'ss.plantation.pay.scheme.tier', 'scheme_id', string="Premium Tiers", copy=True,
        help="Mixed mode: a higher bonus rate for the kilograms far above the basis.")
    holiday_factor = fields.Float(
        string="Sunday / Holiday Factor", default=1.0, digits=(16, 2),
        help="Multiplies the bonus (or piece-rate pay) of a day worked on a Sunday or on a public "
             "holiday of the employee's working calendar. 1 means no extra premium, 2 doubles it.")

    _holiday_factor_min = models.Constraint(
        'CHECK(holiday_factor >= 1)', "The Sunday / Holiday factor cannot be below 1.")

    def _tiered_bonus(self, excess_kg):
        """Bonus for one day with `excess_kg` above the basis. The first band uses the scheme's
        own rate; every tier raises the rate for the kilograms beyond its starting point."""
        self.ensure_one()
        bands = [(0.0, self.bonus_per_kg)] + sorted(
            (tier.above_kg, tier.rate_per_kg) for tier in self.tier_ids)
        total = 0.0
        for i, (start, rate) in enumerate(bands):
            end = bands[i + 1][0] if i + 1 < len(bands) else float('inf')
            if excess_kg > start:
                total += (min(excess_kg, end) - start) * rate
        return total

    @api.model
    def _rest_days(self, employee, date_from, date_to):
        """Sundays and public holidays (company-wide leaves of the employee's calendar) in the period."""
        days = set()
        day = date_from
        while day <= date_to:
            if day.weekday() == 6:
                days.add(day)
            day += timedelta(days=1)
        tz = pytz.timezone(employee.tz or 'UTC')
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('company_id', 'in', [False, employee.company_id.id]),
            ('calendar_id', 'in', [False, employee.resource_calendar_id.id]),
            ('date_to', '>=', datetime.combine(date_from, time.min) - timedelta(days=1)),
            ('date_from', '<=', datetime.combine(date_to, time.max) + timedelta(days=1)),
        ])
        for leave in leaves:
            start = pytz.utc.localize(leave.date_from).astimezone(tz).date()
            end = pytz.utc.localize(leave.date_to).astimezone(tz).date()
            day = max(start, date_from)
            while day <= min(end, date_to):
                days.add(day)
                day += timedelta(days=1)
        return days
