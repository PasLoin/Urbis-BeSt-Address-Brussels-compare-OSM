import { showToast } from './toast.js';

const THUMB_TILE = 'https://tile.openstreetmap.org/16/33560/21984.png';
const ZINNEKE_ATTRIBUTION = '<a href="https://github.com/PasLoin/ZinnekeTiles" target="_blank">ZinnekeTiles</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>';
const ZINNEKE_BASE = 'https://pasloin.github.io/ZinnekeTiles/';
const OVERLAY_SOURCES = ['addresses-source', 'lasso-source'];
const BASEMAP_STORAGE_KEY = 'urbis-osm-basemap';

export const OSM_CARTO_STYLE = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
      maxzoom: 19
    }
  },
  glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf',
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
};

export const BASEMAPS = [
  { id: 'osm', label: 'OSM Carto', short: 'OSM Carto', thumb: THUMB_TILE, style: OSM_CARTO_STYLE },
  {
    id: 'zinneke', label: 'ZinnekeTiles', short: 'Zinneke', thumb: ZINNEKE_BASE + 'assets/img/basemap-zinneke.png',
    url: ZINNEKE_BASE + 'style.json', attribution: ZINNEKE_ATTRIBUTION,
    hideSources: ['public_transport', 'poi'],
    hideLayers: ['railway-tram*', 'railway-subway*', 'railway-tunnel-tram', 'railway-tunnel-subway']
  },
  {
    id: 'nb', label: 'ZinnekeTiles Noir & Blanc', short: 'Zinneke N&B', thumb: ZINNEKE_BASE + 'assets/img/basemap-nb.png',
    url: ZINNEKE_BASE + 'style.nb.json', attribution: ZINNEKE_ATTRIBUTION
  }
];

export function keepOverlays(prev, next) {
  const sources = { ...next.sources };
  for (const id of OVERLAY_SOURCES) {
    if (prev && prev.sources && prev.sources[id]) sources[id] = prev.sources[id];
  }
  const overlayLayers = ((prev && prev.layers) || []).filter(l => OVERLAY_SOURCES.includes(l.source));
  return { ...next, sources, layers: [...next.layers, ...overlayLayers] };
}

async function rasterizeSvg(svgText, size, pixelRatio) {
  const blobUrl = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = blobUrl; });
    const px = Math.round(size * pixelRatio);
    const canvas = document.createElement('canvas');
    canvas.width = px;
    canvas.height = px;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, px, px);
    return ctx.getImageData(0, 0, px, px);
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
}

export function initBasemaps(map) {
  const styleCache = {};
  let currentBasemap = 'osm';
  let request = 0;
  const control = document.getElementById('basemap-control');
  const toggle = document.getElementById('basemap-toggle');
  const menu = document.getElementById('basemap-menu');

  async function loadStyle(bm) {
    if (bm.style) return bm.style;
    if (styleCache[bm.id]) return styleCache[bm.id];
    const res = await fetch(bm.url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const style = await res.json();
    const hideSources = new Set(bm.hideSources || []);
    const hideLayers = bm.hideLayers || [];
    const isHidden = layer => hideSources.has(layer.source) || hideLayers.some(pattern =>
      pattern.endsWith('*') ? layer.id.startsWith(pattern.slice(0, -1)) : layer.id === pattern);
    style.layers = (style.layers || []).filter(layer => !isHidden(layer));
    const usedSources = new Set(style.layers.map(layer => layer.source).filter(Boolean));
    for (const id of Object.keys(style.sources || {})) {
      if (!usedSources.has(id)) delete style.sources[id];
    }
    for (const src of Object.values(style.sources || {})) {
      if (src.url && /\.pmtiles$/.test(src.url)) src.url = 'pmtiles://' + new URL(src.url, bm.url).href;
      if (bm.attribution) src.attribution = bm.attribution;
    }
    for (const layer of style.layers || []) {
      if (layer.layout && layer.layout['icon-image']) {
        layer.layout.visibility = 'none';
        delete layer.layout['icon-image'];
      }
    }
    styleCache[bm.id] = style;
    return style;
  }

  async function loadPatterns(style, baseUrl) {
    const patterns = (style.metadata || {})['brussels:patterns'] || {};
    await Promise.all(Object.entries(patterns).map(async ([name, cfg]) => {
      if (!cfg || !cfg.file || map.hasImage(name)) return;
      try {
        const res = await fetch(new URL(cfg.file, baseUrl).href);
        if (!res.ok) return;
        let svg = await res.text();
        for (const [from, to] of Object.entries(cfg.replace || {})) svg = svg.split(from).join(to);
        const data = await rasterizeSvg(svg, cfg.size || 32, 2);
        if (!map.hasImage(name)) map.addImage(name, data, { pixelRatio: 2 });
      } catch (err) {
        console.warn(`Motif ${name} indisponible :`, err);
      }
    }));
    map.triggerRepaint();
  }

  function renderMenu() {
    menu.replaceChildren(...BASEMAPS.map(bm => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'basemap-option' + (bm.id === currentBasemap ? ' active' : '');
      btn.dataset.id = bm.id;
      btn.setAttribute('role', 'radio');
      btn.setAttribute('aria-checked', bm.id === currentBasemap ? 'true' : 'false');
      btn.title = bm.label;
      btn.setAttribute('aria-label', bm.label);
      const img = document.createElement('img');
      img.src = bm.thumb;
      img.alt = '';
      img.loading = 'lazy';
      if (bm.thumbFilter) img.style.filter = bm.thumbFilter;
      const span = document.createElement('span');
      span.textContent = bm.short || bm.label;
      btn.append(img, span);
      btn.addEventListener('click', () => setBasemap(bm.id));
      return btn;
    }));
  }

  async function setBasemap(id) {
    const bm = BASEMAPS.find(b => b.id === id);
    if (!bm || id === currentBasemap) return;
    const current = ++request;
    const btn = document.querySelector(`.basemap-option[data-id="${id}"]`);
    if (btn) btn.classList.add('loading');
    try {
      const style = await loadStyle(bm);
      if (current !== request) return;
      currentBasemap = id;
      if (bm.url) map.once('style.load', () => loadPatterns(style, bm.url));
      map.setStyle(style, { diff: false, transformStyle: keepOverlays });
      try { localStorage.setItem(BASEMAP_STORAGE_KEY, id); } catch (e) {}
      renderMenu();
    } catch (err) {
      console.error('Fond de carte indisponible :', err);
      showToast('Fond de carte indisponible');
      if (btn) btn.classList.remove('loading');
    }
  }

  function setMenuOpen(open) {
    control.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  toggle.addEventListener('click', e => {
    e.stopPropagation();
    setMenuOpen(!control.classList.contains('open'));
  });
  document.addEventListener('click', e => {
    if (!control.contains(e.target)) setMenuOpen(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') setMenuOpen(false);
  });

  renderMenu();
  map.once('load', () => {
    let saved = null;
    try { saved = localStorage.getItem(BASEMAP_STORAGE_KEY); } catch (e) {}
    if (saved && saved !== currentBasemap) setBasemap(saved);
  });

  return { renderMenu, setBasemap };
}
