import { NON_EXPORTABLE } from './statuses.js';
import { pointInPolygon } from './geometry.js';
import { downloadOsmXml } from './osm-export.js';
import { ADDRESS_LAYER } from './filters.js';

export const LASSO_SOURCE = 'lasso-source';
const MIN_DIST = 10;
const EMPTY = { type: 'FeatureCollection', features: [] };

export function addLassoLayers(map) {
  map.addSource(LASSO_SOURCE, { type: 'geojson', data: EMPTY });
  map.addLayer({ id: 'lasso-fill', type: 'fill', source: LASSO_SOURCE, paint: { 'fill-color': '#3498db', 'fill-opacity': 0.15 } });
  map.addLayer({ id: 'lasso-line', type: 'line', source: LASSO_SOURCE, paint: { 'line-color': '#2980b9', 'line-width': 2, 'line-dasharray': [3, 2] } });
}

export function initLasso(map) {
  let active = false;
  let drawing = false;
  let points = [];
  let selected = [];
  let lastPx = null;
  const button = document.getElementById('lasso-btn');
  const panel = document.getElementById('lasso-panel');
  const countEl = document.getElementById('lasso-count');
  const canvas = map.getCanvas();

  function updatePolygon() {
    const src = map.getSource(LASSO_SOURCE);
    if (!src) return;
    if (points.length < 2) { src.setData(EMPTY); return; }
    const coords = points.map(p => [p.lng, p.lat]);
    const geometry = points.length >= 3
      ? { type: 'Polygon', coordinates: [[...coords, coords[0]]] }
      : { type: 'LineString', coordinates: coords };
    src.setData({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry }] });
  }

  function resetSelection() {
    points = [];
    selected = [];
    updatePolygon();
    panel.style.display = 'none';
  }

  function toggle() {
    active = !active;
    drawing = false;
    button.classList.toggle('active', active);
    if (active) {
      points = [];
      selected = [];
      canvas.style.cursor = 'crosshair';
      map.dragPan.disable();
      updatePolygon();
      panel.style.display = 'none';
    } else {
      canvas.style.cursor = '';
      map.dragPan.enable();
      points = [];
      updatePolygon();
      panel.style.display = 'none';
    }
  }

  function finish() {
    if (points.length < 3) { points = []; updatePolygon(); return; }
    const polygon = points.map(p => [p.lng, p.lat]);
    const features = map.queryRenderedFeatures({ layers: [ADDRESS_LAYER] });
    const seen = new Set();
    selected = [];
    for (const f of features) {
      if (NON_EXPORTABLE.has(f.properties.status)) continue;
      const coords = f.geometry.coordinates;
      const key = `${coords[0]},${coords[1]}`;
      if (seen.has(key)) continue;
      seen.add(key);
      if (pointInPolygon(coords, polygon)) {
        selected.push({ properties: f.properties, lng: coords[0], lat: coords[1], geometry: f.geometry });
      }
    }
    countEl.textContent = selected.length;
    panel.style.display = 'block';
    active = false;
    drawing = false;
    button.classList.remove('active');
    canvas.style.cursor = '';
    map.dragPan.enable();
  }

  function start(x, y) {
    drawing = true;
    points = [];
    lastPx = { x, y };
    const ll = map.unproject([x, y]);
    points.push({ lng: ll.lng, lat: ll.lat });
  }

  function extend(x, y) {
    const dx = x - lastPx.x;
    const dy = y - lastPx.y;
    if (dx * dx + dy * dy < MIN_DIST * MIN_DIST) return;
    lastPx = { x, y };
    const ll = map.unproject([x, y]);
    points.push({ lng: ll.lng, lat: ll.lat });
    updatePolygon();
  }

  function touchPoint(e) {
    const touch = e.touches[0];
    const rect = canvas.getBoundingClientRect();
    return { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
  }

  button.addEventListener('click', toggle);
  document.getElementById('lasso-export').addEventListener('click', () => {
    if (selected.length) downloadOsmXml(selected, 'addresses-selection.osm');
  });
  document.getElementById('lasso-cancel').addEventListener('click', resetSelection);

  canvas.addEventListener('mousedown', e => {
    if (!active || e.button !== 0) return;
    e.preventDefault();
    start(e.offsetX, e.offsetY);
  });
  canvas.addEventListener('mousemove', e => {
    if (!active || !drawing) return;
    extend(e.offsetX, e.offsetY);
  });
  document.addEventListener('mouseup', e => {
    if (!active || !drawing || e.button !== 0) return;
    drawing = false;
    finish();
  });
  canvas.addEventListener('touchstart', e => {
    if (!active) return;
    e.preventDefault();
    const { x, y } = touchPoint(e);
    start(x, y);
  }, { passive: false });
  canvas.addEventListener('touchmove', e => {
    if (!active || !drawing) return;
    e.preventDefault();
    const { x, y } = touchPoint(e);
    extend(x, y);
  }, { passive: false });
  document.addEventListener('touchend', () => {
    if (!active || !drawing) return;
    drawing = false;
    finish();
  });

  function handleEscape() {
    if (active) {
      drawing = false;
      toggle();
      return true;
    }
    drawing = false;
    resetSelection();
    return false;
  }

  return { isActive: () => active, handleEscape };
}
