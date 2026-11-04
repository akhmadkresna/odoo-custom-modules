from odoo import fields, models


class SsPlantationFfbPrice(models.Model):
    _name = 'ss.plantation.ffb.price'
    _description = 'Plantation FFB Reference Price'
    _order = 'date_from desc, id desc'

    date_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    price_per_kg = fields.Monetary(required=True, currency_field='currency_id')
    partner_category_id = fields.Many2one(
        'res.partner.category', string="Supplier Tag",
        help="Leave empty for a price valid for every supplier.")

    _price_positive = models.Constraint('CHECK(price_per_kg >= 0)', "The price cannot be negative.")

    def _get_price(self, company, date, partner=None):
        """Latest price valid at `date`, preferring one matching a tag of `partner`."""
        domain = [('company_id', '=', company.id), ('date_from', '<=', date)]
        prices = self.search(domain)
        tags = partner.category_id if partner else self.env['res.partner.category']
        specific = prices.filtered(lambda p: p.partner_category_id and p.partner_category_id in tags)
        general = prices.filtered(lambda p: not p.partner_category_id)
        for candidates in (specific, general):
            if candidates:
                return candidates[0].price_per_kg
        return 0.0
