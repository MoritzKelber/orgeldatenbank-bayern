import L from "leaflet";
import { fixText } from "./textfix";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import "leaflet.markercluster";
// The `?url` suffix matters: without it, Astro's built-in image pipeline
// turns these imports into `{src, width, height}` objects instead of
// plain URL strings, which made Leaflet request a literal
// ".../[object Object]" path (a real 404 caught via Lighthouse's
// errors-in-console audit).
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png?url";
import markerIcon from "leaflet/dist/images/marker-icon.png?url";
import markerShadow from "leaflet/dist/images/marker-shadow.png?url";

// Vite bundles Leaflet's marker images under hashed URLs, which breaks
// Leaflet's own default-icon path lookup unless re-pointed like this.
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// Three independent geographic precision levels - see
// etl/src/geocode/{build_kirchen_layer,geocode,build_landkreise_layer}.py.
// Kept as separate datasets/layers rather than collapsed into one pin,
// so the map can show (and the viewer can tell apart) a building-exact
// church position, a village-level estimate, and a county-level
// fallback that covers organs with no finer coordinate at all.

interface PlaceOrgan {
  id: number;
  kirche: string | null;
  jahr_anzeige: string | null;
}

interface Place {
  place_key: string;
  lat: number;
  lon: number;
  ort: string | null;
  landkreis: string | null;
  organs: PlaceOrgan[];
}

interface PlacesFile {
  places: Place[];
  organs_ohne_koordinate: number;
}

interface KircheOrgan {
  id: number;
  jahr_anzeige: string | null;
}

interface Kirche {
  key: string;
  lat: number;
  lon: number;
  kirche: string | null;
  ort: string | null;
  landkreis: string | null;
  quelle: "wikidata_via_gnd_kirche" | "kbb_pfarramt" | null;
  gnd_url: string | null;
  organs: KircheOrgan[];
}

interface KirchenFile {
  kirchen: Kirche[];
}

interface Landkreis {
  name: string;
  ist_kreisfreie_stadt: boolean;
  lat: number;
  lon: number;
  anzahl_orgeln: number;
  anzahl_orte: number;
}

interface LandkreiseFile {
  landkreise: Landkreis[];
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = fixText(text);
  return div.innerHTML;
}

function placePopupHtml(place: Place, base: string): string {
  const title = [place.ort, place.landkreis].filter(Boolean).join(" · ");
  const items = place.organs
    .map((o) => {
      const label = o.kirche ?? `Orgel ${o.id}`;
      const suffix = o.jahr_anzeige ? ` (${o.jahr_anzeige})` : "";
      return `<li><a href="${base}/orgeln/${o.id}/">${escapeHtml(label)}${escapeHtml(suffix)}</a></li>`;
    })
    .join("");
  return `<strong>${escapeHtml(title)}</strong><ul class="map-popup-list">${items}</ul>`;
}

function kirchePopupHtml(kirche: Kirche, base: string): string {
  const title = [kirche.kirche, kirche.ort].filter(Boolean).join(" · ");
  const items = kirche.organs
    .map((o) => {
      const suffix = o.jahr_anzeige ? ` (${o.jahr_anzeige})` : "";
      return `<li><a href="${base}/orgeln/${o.id}/">Orgel ${o.id}${escapeHtml(suffix)}</a></li>`;
    })
    .join("");
  const source = kirche.gnd_url
    ? `<p class="map-popup-gnd"><a href="${kirche.gnd_url}" target="_blank" rel="noopener">GND-Eintrag ↗</a></p>`
    : kirche.quelle === "kbb_pfarramt"
      ? `<p class="map-popup-gnd">Quelle: Pfarramts-Adresse (Katholisches Büro Bayern)</p>`
      : "";
  return `<strong>${escapeHtml(title)}</strong><ul class="map-popup-list">${items}</ul>${source}`;
}

function landkreisPopupHtml(lkr: Landkreis): string {
  const label = lkr.ist_kreisfreie_stadt ? `Stadt ${lkr.name} (kreisfreie Stadt)` : `Landkreis ${lkr.name}`;
  return `<strong>${escapeHtml(label)}</strong><p>${lkr.anzahl_orgeln.toLocaleString("de-DE")} Orgeln in ${lkr.anzahl_orte.toLocaleString("de-DE")} Orten</p>`;
}

export async function initOrganMap(opts: { mapElementId: string; statusElementId: string; base: string }) {
  const statusEl = document.getElementById(opts.statusElementId);
  const mapEl = document.getElementById(opts.mapElementId);
  if (!mapEl) return;

  const map = L.map(mapEl).setView([48.95, 11.4], 7); // Bavaria, roughly centered
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
  }).addTo(map);

  try {
    const [placesRes, kirchenRes, landkreiseRes] = await Promise.all([
      fetch(`${opts.base}/data/places.json`),
      fetch(`${opts.base}/data/kirchen.json`),
      fetch(`${opts.base}/data/landkreise.json`),
    ]);
    const placesData: PlacesFile = await placesRes.json();
    const kirchenData: KirchenFile = await kirchenRes.json();
    const landkreiseData: LandkreiseFile = await landkreiseRes.json();

    const ortLayer = (L as any).markerClusterGroup();
    for (const place of placesData.places) {
      const marker = L.marker([place.lat, place.lon]);
      marker.bindPopup(placePopupHtml(place, opts.base));
      ortLayer.addLayer(marker);
    }

    const kircheIcon = L.icon({
      iconUrl: markerIcon, iconRetinaUrl: markerIcon2x, shadowUrl: markerShadow,
      iconSize: [20, 33], iconAnchor: [10, 33], className: "marker-kirche",
    });
    const kircheLayer = (L as any).markerClusterGroup();
    for (const kirche of kirchenData.kirchen) {
      const marker = L.marker([kirche.lat, kirche.lon], { icon: kircheIcon });
      marker.bindPopup(kirchePopupHtml(kirche, opts.base));
      kircheLayer.addLayer(marker);
    }

    const landkreisIcon = L.icon({
      iconUrl: markerIcon, iconRetinaUrl: markerIcon2x, shadowUrl: markerShadow,
      iconSize: [30, 49], iconAnchor: [15, 49], className: "marker-landkreis",
    });
    const landkreisLayer = L.layerGroup();
    for (const lkr of landkreiseData.landkreise) {
      const marker = L.marker([lkr.lat, lkr.lon], { icon: landkreisIcon });
      marker.bindPopup(landkreisPopupHtml(lkr));
      landkreisLayer.addLayer(marker);
    }

    ortLayer.addTo(map);
    L.control
      .layers(
        {},
        {
          "Orte (Dorf/Stadt-Mitte)": ortLayer,
          "Kirchen (gebäudegenau)": kircheLayer,
          "Landkreise (Übersicht)": landkreisLayer,
        },
        { collapsed: false },
      )
      .addTo(map);

    if (statusEl) {
      const totalOrgans = placesData.places.reduce((sum, p) => sum + p.organs.length, 0);
      statusEl.textContent =
        `${placesData.places.length.toLocaleString("de-DE")} Orte mit ${totalOrgans.toLocaleString("de-DE")} Orgeln auf der Karte` +
        (placesData.organs_ohne_koordinate > 0
          ? ` · ${placesData.organs_ohne_koordinate.toLocaleString("de-DE")} Orgeln ohne Orts-Koordinate (aber auf der Landkreis-Ebene sichtbar)`
          : "") +
        ` · ${kirchenData.kirchen.length.toLocaleString("de-DE")} Kirchen gebäudegenau verortet`;
    }
  } catch {
    if (statusEl) statusEl.textContent = "Kartendaten konnten nicht geladen werden.";
  }
}
