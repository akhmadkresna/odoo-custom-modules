"""Small GeoJSON helpers: validation, centroid and area.

No third-party dependency. Areas use a local flat projection, which is accurate
enough (well under 1%) for plantation-sized shapes.
"""
import json
import math

EARTH_RADIUS_M = 6371008.8

# geometry kind used by the widget and by landmark types -> GeoJSON types
KIND_TYPES = {
    'point': ('Point',),
    'line': ('LineString',),
    'polygon': ('Polygon', 'MultiPolygon'),
}
KIND_TYPES['area'] = KIND_TYPES['polygon']


def _is_position(pos):
    return (
        isinstance(pos, (list, tuple))
        and len(pos) >= 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pos[:2])
        and -180 <= pos[0] <= 180
        and -90 <= pos[1] <= 90
    )


def _check_ring(ring):
    if not isinstance(ring, list) or len(ring) < 4 or not all(map(_is_position, ring)):
        raise ValueError("A polygon ring needs at least 4 valid positions.")
    if list(ring[0][:2]) != list(ring[-1][:2]):
        raise ValueError("A polygon ring must be closed (first and last point equal).")
    if len({tuple(p[:2]) for p in ring[:-1]}) < 3:
        raise ValueError("A polygon needs at least 3 distinct points.")


def _check_polygon(rings):
    if not isinstance(rings, list) or not rings:
        raise ValueError("A polygon needs at least one ring.")
    for ring in rings:
        _check_ring(ring)


def parse_geometry(text, kind=None):
    """Return the geometry dict of a GeoJSON string, or None when empty.

    :param text: GeoJSON geometry as a string
    :param kind: optional key of KIND_TYPES restricting the allowed types
    :raises ValueError: with a user readable message when invalid
    """
    if not text or not text.strip():
        return None
    try:
        geom = json.loads(text)
    except ValueError:
        raise ValueError("The geometry is not valid JSON.") from None
    if not isinstance(geom, dict) or 'type' not in geom or 'coordinates' not in geom:
        raise ValueError("Expected a GeoJSON geometry with 'type' and 'coordinates'.")
    gtype, coords = geom['type'], geom['coordinates']
    allowed = KIND_TYPES[kind] if kind else ('Point', 'LineString', 'Polygon', 'MultiPolygon')
    if gtype not in allowed:
        raise ValueError("Geometry type %s is not allowed here (expected %s)." % (gtype, ", ".join(allowed)))
    if gtype == 'Point':
        if not _is_position(coords):
            raise ValueError("Invalid point: longitude must be in [-180, 180] and latitude in [-90, 90].")
    elif gtype == 'LineString':
        if not isinstance(coords, list) or len(coords) < 2 or not all(map(_is_position, coords)):
            raise ValueError("A line needs at least 2 valid positions.")
    elif gtype == 'Polygon':
        _check_polygon(coords)
    elif gtype == 'MultiPolygon':
        if not isinstance(coords, list) or not coords:
            raise ValueError("A multipolygon needs at least one polygon.")
        for poly in coords:
            _check_polygon(poly)
    return geom


def _project(ring, lat0):
    k = math.cos(math.radians(lat0))
    return [
        (math.radians(p[0]) * EARTH_RADIUS_M * k, math.radians(p[1]) * EARTH_RADIUS_M)
        for p in ring
    ]


def _shoelace(points):
    """Return (signed area, cx, cy) of a closed projected ring."""
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area /= 2.0
    if area:
        cx /= 6.0 * area
        cy /= 6.0 * area
    return area, cx, cy


def _polygons(geom):
    if not geom:
        return []
    if geom.get('type') == 'Polygon':
        return [geom['coordinates']]
    if geom.get('type') == 'MultiPolygon':
        return geom['coordinates']
    return []


def area_ha(geom):
    """Area of a (Multi)Polygon in hectares, holes subtracted. 0.0 otherwise."""
    total = 0.0
    for rings in _polygons(geom):
        lat0 = sum(p[1] for p in rings[0]) / len(rings[0])
        outer = abs(_shoelace(_project(rings[0], lat0))[0])
        holes = sum(abs(_shoelace(_project(r, lat0))[0]) for r in rings[1:])
        total += outer - holes
    return total / 10000.0


def centroid(geom):
    """Return (latitude, longitude) of a geometry, or None."""
    if not geom:
        return None
    gtype, coords = geom['type'], geom['coordinates']
    if gtype == 'Point':
        return coords[1], coords[0]
    if gtype == 'LineString':
        return (sum(p[1] for p in coords) / len(coords), sum(p[0] for p in coords) / len(coords))
    best = None
    for rings in _polygons(geom):
        ring = rings[0]
        lat0 = sum(p[1] for p in ring) / len(ring)
        area, cx, cy = _shoelace(_project(ring, lat0))
        if best is None or abs(area) > best[0]:
            if area:
                k = math.cos(math.radians(lat0))
                lon = math.degrees(cx / (EARTH_RADIUS_M * k))
                lat = math.degrees(cy / EARTH_RADIUS_M)
            else:
                lat = sum(p[1] for p in ring) / len(ring)
                lon = sum(p[0] for p in ring) / len(ring)
            best = (abs(area), lat, lon)
    return (best[1], best[2]) if best else None
