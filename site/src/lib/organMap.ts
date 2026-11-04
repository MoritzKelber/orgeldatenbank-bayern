import L from "leaflet";
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

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function popupHtml(place: Place, base: string): string {
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
    const res = await fetch(`${opts.base}/data/places.json`);
    const data: PlacesFile = await res.json();

    const clusterGroup = (L as any).markerClusterGroup();
    for (const place of data.places) {
      const marker = L.marker([place.lat, place.lon]);
      marker.bindPopup(popupHtml(place, opts.base));
      clusterGroup.addLayer(marker);
    }
    map.addLayer(clusterGroup);

    if (statusEl) {
      const totalOrgans = data.places.reduce((sum, p) => sum + p.organs.length, 0);
      statusEl.textContent =
        `${data.places.length.toLocaleString("de-DE")} Orte mit ${totalOrgans.toLocaleString("de-DE")} Orgeln auf der Karte` +
        (data.organs_ohne_koordinate > 0
          ? ` · ${data.organs_ohne_koordinate.toLocaleString("de-DE")} Orgeln konnten nicht verortet werden`
          : "");
    }
  } catch {
    if (statusEl) statusEl.textContent = "Kartendaten konnten nicht geladen werden.";
  }
}
