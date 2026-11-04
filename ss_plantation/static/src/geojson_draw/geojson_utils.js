/** Helpers shared by the GeoJSON drawing widget and the plantation map. */

export const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const TILE_ATTRIBUTION =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
// Centre of Indonesia, used when nothing is drawn yet.
export const DEFAULT_CENTER = [-1.5, 113.0];
export const DEFAULT_ZOOM = 5;

const KIND_TYPES = {
    point: ["Point"],
    line: ["LineString"],
    polygon: ["Polygon", "MultiPolygon"],
};
KIND_TYPES.area = KIND_TYPES.polygon;

function isPosition(pos) {
    return (
        Array.isArray(pos) &&
        pos.length >= 2 &&
        typeof pos[0] === "number" &&
        typeof pos[1] === "number" &&
        Math.abs(pos[0]) <= 180 &&
        Math.abs(pos[1]) <= 90
    );
}

/**
 * Accept a Geometry, a Feature or a FeatureCollection and return the geometry.
 * @param {Object} data
 * @returns {Object|null}
 */
export function unwrapGeometry(data) {
    if (!data || typeof data !== "object") {
        return null;
    }
    if (data.type === "FeatureCollection") {
        return unwrapGeometry((data.features || [])[0]);
    }
    if (data.type === "Feature") {
        return data.geometry || null;
    }
    return data;
}

/**
 * @param {Object} geom parsed GeoJSON geometry
 * @param {string} kind point | line | polygon | area
 * @returns {string|null} an error message, or null when valid
 */
export function validateGeometry(geom, kind) {
    if (!geom || !geom.type || !geom.coordinates) {
        return "Expected a GeoJSON geometry.";
    }
    const allowed = KIND_TYPES[kind] || ["Point", "LineString", "Polygon", "MultiPolygon"];
    if (!allowed.includes(geom.type)) {
        return `Geometry type ${geom.type} is not allowed here (expected ${allowed.join(" or ")}).`;
    }
    const c = geom.coordinates;
    if (geom.type === "Point") {
        return isPosition(c) ? null : "Invalid point coordinates.";
    }
    if (geom.type === "LineString") {
        return Array.isArray(c) && c.length >= 2 && c.every(isPosition)
            ? null
            : "A line needs at least 2 valid points.";
    }
    const polygons = geom.type === "Polygon" ? [c] : c;
    for (const rings of polygons) {
        for (const ring of rings) {
            if (!Array.isArray(ring) || ring.length < 4 || !ring.every(isPosition)) {
                return "A polygon ring needs at least 4 valid positions.";
            }
            const first = ring[0];
            const last = ring[ring.length - 1];
            if (first[0] !== last[0] || first[1] !== last[1]) {
                return "A polygon ring must be closed.";
            }
            if (new Set(ring.slice(0, -1).map((p) => p.join(","))).size < 3) {
                return "A polygon needs at least 3 distinct points.";
            }
        }
    }
    return null;
}

/** Geometry kind for a widget `geometry` option and an optional record kind. */
export function resolveKind(option, recordKind) {
    const kind = option === "auto" || !option ? recordKind || "point" : option;
    return kind === "area" ? "polygon" : kind;
}

/** Leaflet [lat, lng] points of a simple geometry (outer ring only for polygons). */
export function toLatLngs(geom) {
    if (!geom) {
        return [];
    }
    if (geom.type === "Point") {
        return [[geom.coordinates[1], geom.coordinates[0]]];
    }
    if (geom.type === "LineString") {
        return geom.coordinates.map((p) => [p[1], p[0]]);
    }
    if (geom.type === "Polygon") {
        return geom.coordinates[0].slice(0, -1).map((p) => [p[1], p[0]]);
    }
    return [];
}

/** True when the widget can edit this geometry vertex by vertex. */
export function isSimple(geom) {
    return !geom || ["Point", "LineString"].includes(geom.type) || (
        geom.type === "Polygon" && geom.coordinates.length === 1
    );
}

/** Build a GeoJSON geometry from Leaflet [lat, lng] points, or null when too few. */
export function fromLatLngs(kind, points) {
    const lonLat = points.map(([lat, lng]) => [
        Math.round(lng * 1e7) / 1e7,
        Math.round(lat * 1e7) / 1e7,
    ]);
    if (kind === "point") {
        return lonLat.length >= 1 ? { type: "Point", coordinates: lonLat[0] } : null;
    }
    if (kind === "line") {
        return lonLat.length >= 2 ? { type: "LineString", coordinates: lonLat } : null;
    }
    if (lonLat.length < 3) {
        return null;
    }
    return { type: "Polygon", coordinates: [[...lonLat, lonLat[0]]] };
}
