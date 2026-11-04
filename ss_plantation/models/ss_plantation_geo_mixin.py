from odoo import models
from odoo.exceptions import ValidationError

from ..tools import geo


class SsPlantationGeoMixin(models.AbstractModel):
    _name = 'ss.plantation.geo.mixin'
    _description = 'Plantation GeoJSON helpers'

    def _ss_check_geojson(self, fname, kind):
        """Raise a ValidationError when `fname` holds an invalid or wrong-type geometry."""
        for record in self:
            try:
                geo.parse_geometry(record[fname], kind)
            except ValueError as exc:
                raise ValidationError(self.env._(
                    "%(record)s: %(error)s", record=record.display_name, error=exc,
                )) from exc

    def _ss_geometry(self, fname, kind=None):
        """Parsed geometry of `fname` or None (never raises on stored data)."""
        self.ensure_one()
        try:
            return geo.parse_geometry(self[fname], kind)
        except ValueError:
            return None
