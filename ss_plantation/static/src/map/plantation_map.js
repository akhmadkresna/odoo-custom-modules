import { Component, onMounted, onWillDestroy, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

import {
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
    TILE_ATTRIBUTION,
    TILE_URL,
} from "../geojson_draw/geojson_utils";

const LEAFLET_JS = "/web_map/static/lib/leaflet/leaflet.js";
const LEAFLET_CSS = "/web_map/static/lib/leaflet/leaflet.css";

const STAGE_COLORS = {
    immature: "#f9a825",
    mature: "#2e7d32",
    replanting: "#8e24aa",
    closed: "#757575",
};
// kg per hectare in the last 30 days, from low to high
const YIELD_BANDS = [
    { min: 0, color: "#d73027", label: "0 kg/ha" },
    { min: 1, color: "#fc8d59", label: "< 500" },
    { min: 500, color: "#fee08b", label: "500 - 1,000" },
    { min: 1000, color: "#91cf60", label: "1,000 - 2,000" },
    { min: 2000, color: "#1a9850", label: "2,000+" },
];

function yieldColor(kgPerHa) {
    let color = YIELD_BANDS[0].color;
    for (const band of YIELD_BANDS) {
        if (kgPerHa >= band.min) {
            color = band.color;
        }
    }
    return color;
}

/** Client action: estates, divisions, blocks and landmarks on one map. */
export class PlantationMap extends Component {
    static template = "ss_plantation.PlantationMap";
    props = useProps(standardActionServiceProps);

    mapRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            colorBy: "stage",
            layers: { estates: true, divisions: true, blocks: true, landmarks: true },
            counts: { blocks: 0, landmarks: 0 },
        });
        this.data = { estates: [], divisions: [], blocks: [], landmarks: [] };
        this.groups = {};
        this.stageColors = STAGE_COLORS;
        this.yieldBands = YIELD_BANDS;
        onWillStart(async () => {
            const [data] = await Promise.all([
                this.orm.call("ss.plantation.block", "get_map_data", []),
                loadJS(LEAFLET_JS),
                loadCSS(LEAFLET_CSS),
            ]);
            this.data = data;
        });
        onMounted(() => this.mountMap());
        onWillDestroy(() => {
            this.resizeObserver?.disconnect();
            this.map?.remove();
        });
    }

    mountMap() {
        this.map = L.map(this.mapRef(), { center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM });
        L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(this.map);
        for (const key of Object.keys(this.state.layers)) {
            this.groups[key] = L.layerGroup().addTo(this.map);
        }
        this.resizeObserver = new ResizeObserver(() => this.map.invalidateSize());
        this.resizeObserver.observe(this.mapRef());
        this.draw();
        this.fit();
    }

    draw() {
        for (const group of Object.values(this.groups)) {
            group.clearLayers();
        }
        const outline = (color, weight) => ({ color, weight, fill: false });
        for (const estate of this.data.estates) {
            this.addGeoJson("estates", estate, outline("#1b5e20", 3), "ss.plantation.estate");
        }
        for (const division of this.data.divisions) {
            this.addGeoJson("divisions", division, outline("#455a64", 2), "ss.plantation.division");
        }
        for (const block of this.data.blocks) {
            const color =
                this.state.colorBy === "yield"
                    ? yieldColor(block.yield_kg_ha_30d)
                    : STAGE_COLORS[block.stage] || "#757575";
            this.addGeoJson(
                "blocks",
                block,
                { color: "#263238", weight: 1, fillColor: color, fillOpacity: 0.6 },
                "ss.plantation.block",
                this.blockPopup(block)
            );
        }
        for (const landmark of this.data.landmarks) {
            this.addLandmark(landmark);
        }
        this.state.counts.blocks = this.data.blocks.length;
        this.state.counts.landmarks = this.data.landmarks.length;
    }

    addGeoJson(group, record, style, resModel, popup) {
        let geom;
        try {
            geom = JSON.parse(record.boundary_geojson);
        } catch {
            return;
        }
        const layer = L.geoJSON(geom, { style });
        layer.bindPopup(popup || this.titlePopup(record.name, resModel, record.id));
        layer.addTo(this.groups[group]);
    }

    addLandmark(landmark) {
        let geom;
        try {
            geom = JSON.parse(landmark.geometry_geojson);
        } catch {
            return;
        }
        const type = landmark.type || {};
        const color = type.color || "#3b6e3b";
        const popup = this.titlePopup(
            `${type.icon || ""} ${landmark.name}`,
            "ss.plantation.landmark",
            landmark.id,
            type.name
        );
        const layer = L.geoJSON(geom, {
            style: { color, weight: 3, fillColor: color, fillOpacity: 0.3 },
            pointToLayer: (feature, latlng) =>
                L.marker(latlng, {
                    icon: L.divIcon({
                        className: "o_ss_map_marker",
                        html: `<span style="background:${color}">${type.icon || "📍"}</span>`,
                        iconSize: [30, 30],
                    }),
                }),
        });
        layer.bindPopup(popup);
        layer.addTo(this.groups.landmarks);
    }

    // The popups are plain DOM nodes so the button can open the record.
    titlePopup(title, resModel, resId, subtitle) {
        const root = document.createElement("div");
        const heading = document.createElement("strong");
        heading.textContent = title;
        root.append(heading);
        if (subtitle) {
            const sub = document.createElement("div");
            sub.className = "text-muted";
            sub.textContent = subtitle;
            root.append(sub);
        }
        root.append(this.openButton(resModel, resId));
        return root;
    }

    blockPopup(block) {
        const root = this.titlePopup(
            `${block.code} - ${block.name}`,
            "ss.plantation.block",
            block.id,
            block.division_id ? block.division_id[1] : ""
        );
        const info = document.createElement("div");
        const lines = [
            `${_t("Stage")}: ${block.stage}`,
            `${_t("Area")}: ${block.area_ha.toFixed(2)} ha`,
            `${_t("Last 30 days")}: ${Math.round(block.yield_kg_ha_30d).toLocaleString()} kg/ha`,
            `${_t("Last harvest")}: ${block.last_harvest_date || "-"}`,
        ];
        for (const line of lines) {
            const row = document.createElement("div");
            row.textContent = line;
            info.append(row);
        }
        root.insertBefore(info, root.lastChild);
        return root;
    }

    openButton(resModel, resId) {
        const button = document.createElement("button");
        button.className = "btn btn-sm btn-link p-0 mt-1";
        button.textContent = _t("Open");
        button.addEventListener("click", () =>
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: resModel,
                res_id: resId,
                views: [[false, "form"]],
            })
        );
        return button;
    }

    fit() {
        const bounds = L.latLngBounds([]);
        for (const group of Object.values(this.groups)) {
            group.eachLayer((layer) => {
                if (layer.getBounds) {
                    bounds.extend(layer.getBounds());
                } else if (layer.getLatLng) {
                    bounds.extend(layer.getLatLng());
                }
            });
        }
        if (bounds.isValid()) {
            this.map.fitBounds(bounds, { maxZoom: 16, padding: [30, 30], animate: false });
        }
    }

    onColorByChange(ev) {
        this.state.colorBy = ev.target.value;
        this.draw();
    }

    onToggleLayer(key, ev) {
        this.state.layers[key] = ev.target.checked;
        if (ev.target.checked) {
            this.groups[key].addTo(this.map);
        } else {
            this.groups[key].remove();
        }
    }

    onFit() {
        this.fit();
    }
}

registry.category("actions").add("ss_plantation_map", PlantationMap);
