import { Component, onMounted, onPatched, onWillDestroy, onWillStart, proxy, signal, t, useProps } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import {
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
    TILE_ATTRIBUTION,
    TILE_URL,
    fromLatLngs,
    isSimple,
    resolveKind,
    toLatLngs,
    unwrapGeometry,
    validateGeometry,
} from "./geojson_utils";

const LEAFLET_JS = "/web_map/static/lib/leaflet/leaflet.js";
const LEAFLET_CSS = "/web_map/static/lib/leaflet/leaflet.css";
const MIN_POINTS = { point: 1, line: 2, polygon: 3 };

/**
 * Draw or display a GeoJSON geometry (Text field) on a Leaflet map.
 *
 * Press "Draw shape", click the map to add points, press "Finish". Nothing is
 * written to the record while drawing; "Cancel" keeps the saved shape. Once a
 * shape is saved, drag a point to move it or click a point to remove it. Complex
 * shapes (holes, multipolygons) are displayed but replaced only by drawing again,
 * pasting GeoJSON or clearing.
 */
export class SsGeoJsonDraw extends Component {
    static template = "ss_plantation.GeoJsonDraw";
    props = useProps({
        ...standardFieldProps,
        geometry: t.string().optional(),
        kindField: t.string().optional(),
    });

    mapRef = signal.ref();
    importRef = signal.ref();

    setup() {
        this.state = proxy({ message: "", importing: false, drawing: false, count: 0 });
        this.points = [];
        this.draft = [];
        this.complex = null;
        this.lastValue = undefined;
        onWillStart(() => Promise.all([loadJS(LEAFLET_JS), loadCSS(LEAFLET_CSS)]));
        onMounted(() => this.mountMap());
        onPatched(() => this.syncFromValue());
        onWillDestroy(() => this.destroyMap());
    }

    kind() {
        const recordKind = this.props.kindField
            ? this.props.record.data[this.props.kindField]
            : undefined;
        return resolveKind(this.props.geometry, recordKind);
    }

    minPoints() {
        return MIN_POINTS[this.kind()];
    }

    value() {
        return this.props.record.data[this.props.name] || "";
    }

    canEdit() {
        return !this.props.readonly;
    }

    hasShape() {
        return Boolean(this.complex) || this.points.length > 0 || Boolean(this.value());
    }

    // ------------------------------------------------------------------
    // Map lifecycle
    // ------------------------------------------------------------------
    mountMap() {
        const container = this.mapRef();
        this.map = L.map(container, { center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM });
        L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(this.map);
        this.layerGroup = L.layerGroup().addTo(this.map);
        this.map.on("click", (ev) => this.onMapClick(ev));
        // The map sits in a notebook page or a collapsed group: re-measure when shown.
        this.resizeObserver = new ResizeObserver(() => {
            this.map.invalidateSize();
            if (!this.fitted) {
                this.fit();
            }
        });
        this.resizeObserver.observe(container);
        this.syncFromValue(true);
    }

    destroyMap() {
        this.resizeObserver?.disconnect();
        this.map?.remove();
        this.map = null;
    }

    /** Reload the shape when the record value changed from outside (discard, save, onchange). */
    syncFromValue(force = false) {
        if (this.committing) {
            return; // our own update is in flight; the record value is not up to date yet
        }
        const value = this.value();
        if (!force && value === this.lastValue) {
            return;
        }
        this.lastValue = value;
        this.points = [];
        this.complex = null;
        this.fitted = false;
        if (this.state.drawing) {
            this.stopDrawing();
        }
        if (value) {
            try {
                const geom = JSON.parse(value);
                if (isSimple(geom)) {
                    this.points = toLatLngs(geom);
                } else {
                    this.complex = geom;
                }
            } catch {
                this.state.message = _t("The stored value is not valid GeoJSON.");
            }
        }
        this.render();
        this.fit();
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------
    render() {
        if (!this.map) {
            return;
        }
        this.layerGroup.clearLayers();
        const kind = this.kind();
        this.map.getContainer().classList.toggle("o_ss_geojson_drawing", this.state.drawing);
        // Shapes are not interactive so that clicks reach the map.
        const saved = { color: "#2e7d32", weight: 2, fillOpacity: 0.2, interactive: false };
        if (this.state.drawing) {
            // The saved shape stays visible, faded, so it is clear it will be replaced.
            const faded = { ...saved, color: "#9e9e9e", dashArray: "4 6", fillOpacity: 0.05 };
            if (this.complex) {
                L.geoJSON(this.complex, { style: faded }).addTo(this.layerGroup);
            } else {
                this.addShape(kind, this.points, faded);
            }
            const draft = { color: "#e65100", weight: 3, dashArray: "6 4", fillOpacity: 0.15, interactive: false };
            this.addShape(kind, this.draft, draft);
            this.draft.forEach((latlng, index) => {
                L.marker(latlng, {
                    interactive: false,
                    icon: L.divIcon({
                        className: "o_ss_geojson_draft_point",
                        html: `<span>${index + 1}</span>`,
                        iconSize: [22, 22],
                    }),
                }).addTo(this.layerGroup);
            });
            this.state.count = this.draft.length;
            return;
        }
        if (this.complex) {
            L.geoJSON(this.complex, { style: saved }).addTo(this.layerGroup);
        } else {
            this.addShape(kind, this.points, saved);
            if (this.canEdit()) {
                this.points.forEach((latlng, index) => this.addHandle(latlng, index));
            }
        }
        this.state.count = this.points.length;
    }

    addShape(kind, points, style) {
        if (kind === "polygon" && points.length >= 3) {
            L.polygon(points, style).addTo(this.layerGroup);
        } else if (kind !== "point" && points.length >= 2) {
            L.polyline(points, style).addTo(this.layerGroup);
        } else if (kind === "point" && points.length) {
            L.circleMarker(points[0], { ...style, radius: 6 }).addTo(this.layerGroup);
        }
    }

    addHandle(latlng, index) {
        const marker = L.marker(latlng, {
            draggable: true,
            icon: L.divIcon({ className: "o_ss_geojson_handle", iconSize: [14, 14] }),
        });
        marker.on("dragend", () => {
            const { lat, lng } = marker.getLatLng();
            this.points[index] = [lat, lng];
            this.commit();
        });
        marker.on("click", (ev) => {
            L.DomEvent.stopPropagation(ev);
            this.removePoint(index);
        });
        marker.addTo(this.layerGroup);
    }

    fit() {
        if (!this.map) {
            return;
        }
        const size = this.map.getSize();
        if (!size.x || !size.y) {
            return;
        }
        const bounds = this.complex
            ? L.geoJSON(this.complex).getBounds()
            : this.points.length
              ? L.latLngBounds(this.points)
              : null;
        if (bounds && bounds.isValid()) {
            this.map.fitBounds(bounds, { maxZoom: 17, padding: [20, 20], animate: false });
        } else if (!this.fitted) {
            // Nothing drawn: keep the current view when the shape is cleared.
            this.map.setView(DEFAULT_CENTER, DEFAULT_ZOOM, { animate: false });
        }
        this.fitted = true;
    }

    // ------------------------------------------------------------------
    // Editing: nothing is saved while drawing until Finish is pressed
    // ------------------------------------------------------------------
    onStartDraw() {
        this.draft = [];
        this.state.message = "";
        this.state.importing = false;
        this.state.drawing = true;
        this.map.doubleClickZoom.disable();
        this.render();
    }

    onMapClick(ev) {
        if (!this.canEdit() || !this.state.drawing) {
            return;
        }
        const point = [ev.latlng.lat, ev.latlng.lng];
        if (this.kind() === "point") {
            this.draft = [point];
            this.onFinish();
            return;
        }
        this.draft.push(point);
        this.state.message = "";
        this.render();
    }

    onUndo() {
        this.draft.pop();
        this.render();
    }

    onCancel() {
        this.stopDrawing();
        this.render();
    }

    onFinish() {
        if (this.draft.length < this.minPoints()) {
            this.state.message = _t("Add at least %s points, then press Finish.", this.minPoints());
            return;
        }
        this.points = this.draft;
        this.complex = null;
        this.stopDrawing();
        this.fit();
        this.commit();
    }

    onClear() {
        this.stopDrawing();
        this.points = [];
        this.complex = null;
        this.commit();
    }

    stopDrawing() {
        this.draft = [];
        this.state.drawing = false;
        this.state.message = "";
        this.map?.doubleClickZoom.enable();
    }

    removePoint(index) {
        if (this.points.length <= this.minPoints()) {
            this.state.message = _t(
                "A shape needs at least %s points. Use Clear to remove it.",
                this.minPoints()
            );
            return;
        }
        this.points.splice(index, 1);
        this.commit();
    }

    /** Write the finished shape (or nothing) to the record and redraw. */
    async commit() {
        this.state.message = "";
        const geom = this.points.length ? fromLatLngs(this.kind(), this.points) : null;
        this.render();
        const value = geom ? JSON.stringify(geom) : false;
        this.lastValue = value || "";
        this.committing = true;
        try {
            await this.props.record.update({ [this.props.name]: value });
        } finally {
            this.committing = false;
        }
        this.render();
    }

    // ------------------------------------------------------------------
    // Paste GeoJSON
    // ------------------------------------------------------------------
    onToggleImport() {
        this.state.importing = !this.state.importing;
    }

    async onApplyImport() {
        const text = this.importRef().value.trim();
        if (!text) {
            return;
        }
        let geom;
        try {
            geom = unwrapGeometry(JSON.parse(text));
        } catch {
            this.state.message = _t("This is not valid JSON.");
            return;
        }
        const error = validateGeometry(geom, this.kind());
        if (error) {
            this.state.message = error;
            return;
        }
        this.state.importing = false;
        this.stopDrawing();
        this.lastValue = JSON.stringify(geom);
        this.committing = true;
        try {
            await this.props.record.update({ [this.props.name]: this.lastValue });
        } finally {
            this.committing = false;
        }
        this.syncFromValue(true);
    }
}

registry.category("fields").add("ss_geojson_draw", {
    component: SsGeoJsonDraw,
    displayName: _t("GeoJSON Drawing"),
    supportedTypes: ["text"],
    extractProps: ({ options }) => ({
        geometry: options.geometry,
        kindField: options.kind_field,
    }),
});
