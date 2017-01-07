# import basic odoo library for creating object and field
from openerp import models, fields, api

# declare new pbject/class. "productTemplate" is a new name.
# you could name it as you want
class productTemplate(models.Model):
	# inherit odoo object where you want add a new field
    _inherit = 'product.template'

    # declase your new field
    custom_field = fields.Char('Custom field')


