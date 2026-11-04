import csv
import io
import json

from odoo import fields, models
from odoo.exceptions import UserError

from ..tools import geo


class SsPlantationLandmarkImport(models.TransientModel):
    _name = 'ss.plantation.landmark.import'
    _description = 'Import Plantation Landmarks'

    file = fields.Binary(required=True)
    filename = fields.Char()
    type_id = fields.Many2one(
        'ss.plantation.landmark.type', string="Default Type", required=True,
        help="Used for rows or features that do not name a known type.")
    estate_id = fields.Many2one('ss.plantation.estate')

    def _features(self, text):
        """Yield (name, type_name, geometry dict) from GeoJSON text or CSV (name,type,lat,lon)."""
        stripped = text.lstrip()
        if stripped.startswith('{'):
            data = json.loads(stripped)
            features = data.get('features', [data]) if data.get('type') != 'Feature' else [data]
            for feature in features:
                props = feature.get('properties') or {}
                geometry = feature.get('geometry') or feature
                yield props.get('name') or '', props.get('type') or '', geometry
        else:
            for row in csv.DictReader(io.StringIO(text)):
                try:
                    point = {'type': 'Point', 'coordinates': [float(row['lon']), float(row['lat'])]}
                except (KeyError, TypeError, ValueError):
                    raise UserError(self.env._(
                        "CSV rows need the columns name, type, lat, lon.")) from None
                yield row.get('name') or '', row.get('type') or '', point

    def action_import(self):
        self.ensure_one()
        try:
            text = bytes(self.file).decode('utf-8-sig')
            rows = list(self._features(text))
        except (ValueError, UnicodeDecodeError) as exc:
            raise UserError(self.env._("The file could not be read: %s", exc)) from exc
        types = {t.name.lower(): t for t in self.env['ss.plantation.landmark.type'].search([])}
        vals_list = []
        for index, (name, type_name, geometry) in enumerate(rows, start=1):
            landmark_type = types.get(type_name.lower(), self.type_id)
            try:
                geo.parse_geometry(json.dumps(geometry), landmark_type.geometry_kind)
            except ValueError as exc:
                raise UserError(self.env._("Row %(row)s: %(error)s", row=index, error=exc)) from exc
            vals_list.append({
                'name': name or self.env._("Landmark %s", index),
                'type_id': landmark_type.id,
                'estate_id': self.estate_id.id,
                'geometry_geojson': json.dumps(geometry),
            })
        landmarks = self.env['ss.plantation.landmark'].create(vals_list)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Imported landmarks"),
            'res_model': 'ss.plantation.landmark',
            'view_mode': 'list,form',
            'domain': [('id', 'in', landmarks.ids)],
        }
