from odoo import fields, models


class SsPlantationPaySchemeTier(models.Model):
    """A higher bonus rate that starts once a harvester is a given number of kg above the basis."""
    _name = 'ss.plantation.pay.scheme.tier'
    _description = 'Plantation Pay Scheme Premium Tier'
    _order = 'scheme_id, above_kg'

    scheme_id = fields.Many2one(
        'ss.plantation.pay.scheme', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='scheme_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='scheme_id.currency_id')
    above_kg = fields.Float(
        string="From kg above Basis", digits=(16, 1), required=True,
        help="The rate below applies to the kilograms above the basis beyond this point.")
    rate_per_kg = fields.Monetary(
        string="Bonus / kg", currency_field='currency_id', required=True)

    _above_kg_positive = models.Constraint(
        'CHECK(above_kg > 0)',
        "A premium tier must start above zero. The first band uses the scheme's Bonus / kg above Basis.")
    _above_kg_unique = models.Constraint(
        'UNIQUE(scheme_id, above_kg)', "Two tiers of the same scheme cannot start at the same point.")
    _rate_not_negative = models.Constraint(
        'CHECK(rate_per_kg >= 0)', "The bonus per kg cannot be negative.")
