# import basic odoo library for creating object and field
from openerp import models, fields, api

# declare new pbject/class. "productTemplate" is a new name.
# you could name it as you want
class SaleOrder(models.Model):
	# inherit odoo object where you want add a new field
    _inherit = 'sale.order'

    # declase your new field
    delivery_currier = fields.Char('Delivery Currier')


