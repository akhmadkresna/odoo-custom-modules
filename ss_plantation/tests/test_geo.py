import base64
import json

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..tools import geo
from .common import SsPlantationCommon

SQUARE = {
    'type': 'Polygon',
    # roughly 1 km x 1 km at the equator
    'coordinates': [[[100.0, 0.0], [100.009, 0.0], [100.009, 0.009], [100.0, 0.009], [100.0, 0.0]]],
}


@tagged('post_install', '-at_install')
class TestGeoTools(TransactionCase):

    def test_area_and_centroid(self):
        self.assertAlmostEqual(geo.area_ha(SQUARE), 100.0, delta=2.0)
        lat, lon = geo.centroid(SQUARE)
        self.assertAlmostEqual(lat, 0.0045, places=4)
        self.assertAlmostEqual(lon, 100.0045, places=4)

    def test_empty_geometry_is_safe(self):
        for empty in (None, {}):
            self.assertEqual(geo.area_ha(empty), 0.0)
            self.assertIsNone(geo.centroid(empty))

    def test_parse_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            geo.parse_geometry('not json')
        with self.assertRaises(ValueError):
            geo.parse_geometry(json.dumps({'type': 'Point', 'coordinates': [200, 0]}))
        with self.assertRaises(ValueError):
            geo.parse_geometry(json.dumps({'type': 'LineString', 'coordinates': [[0, 0]]}))
        open_ring = {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
        with self.assertRaises(ValueError):
            geo.parse_geometry(json.dumps(open_ring))
        with self.assertRaises(ValueError):
            geo.parse_geometry(json.dumps({'type': 'Point', 'coordinates': [1, 1]}), 'polygon')

    def test_parse_accepts_valid(self):
        self.assertIsNone(geo.parse_geometry(''))
        self.assertEqual(geo.parse_geometry(json.dumps(SQUARE), 'polygon')['type'], 'Polygon')


@tagged('post_install', '-at_install')
class TestGeoModels(SsPlantationCommon):

    def test_block_boundary_sets_centre_and_suggested_area(self):
        self.block.boundary_geojson = json.dumps(SQUARE)
        self.assertAlmostEqual(self.block.latitude, 0.0045, places=4)
        self.assertAlmostEqual(self.block.suggested_area_ha, 100.0, delta=2.0)
        self.assertEqual(self.block.area_ha, 25.0, "the drawn area never overwrites the area")

    def test_geometry_validation(self):
        with self.assertRaises(ValidationError):
            self.block.boundary_geojson = json.dumps({'type': 'Point', 'coordinates': [1, 1]})
        with self.assertRaises(ValidationError):
            self.estate.boundary_geojson = '{"type": "Polygon"}'

    def test_landmark_kind_matches_type(self):
        road = self.env.ref('ss_plantation.landmark_type_road')
        mill = self.env.ref('ss_plantation.landmark_type_mill')
        line = {'type': 'LineString', 'coordinates': [[100, 0], [100.1, 0.1]]}
        point = {'type': 'Point', 'coordinates': [100.5, 0.5]}
        landmark = self.env['ss.plantation.landmark'].create({
            'name': 'Main road', 'type_id': road.id, 'geometry_geojson': json.dumps(line)})
        self.assertAlmostEqual(landmark.latitude, 0.05, places=3)
        with self.assertRaises(ValidationError):
            self.env['ss.plantation.landmark'].create({
                'name': 'Bad mill', 'type_id': mill.id, 'geometry_geojson': json.dumps(line)})
        mill_landmark = self.env['ss.plantation.landmark'].create({
            'name': 'Mill', 'type_id': mill.id, 'geometry_geojson': json.dumps(point)})
        self.assertEqual(mill_landmark.longitude, 100.5)

    def test_landmark_import_csv(self):
        wizard = self.env['ss.plantation.landmark.import'].create({
            'file': base64.b64encode(b"name,type,lat,lon\nGate,Mill,0.1,100.2\n").decode(),
            'filename': 'landmarks.csv',
            'type_id': self.env.ref('ss_plantation.landmark_type_office').id,
        })
        action = wizard.action_import()
        landmark = self.env['ss.plantation.landmark'].search(action['domain'])
        self.assertEqual(landmark.type_id, self.env.ref('ss_plantation.landmark_type_mill'))

    def test_map_data(self):
        self.block.boundary_geojson = json.dumps(SQUARE)
        data = self.env['ss.plantation.block'].get_map_data()
        self.assertIn(self.block.id, [b['id'] for b in data['blocks']])
