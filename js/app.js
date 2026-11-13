import { i18nFromDocument, setI18n } from './i18n.js';
import { statusColorExpression } from './statuses.js';
import { renderStats, renderVersionInfo } from './stats.js';
import { initFilters, ADDRESS_LAYER } from './filters.js';
import { OSM_CARTO_STYLE, initBasemaps } from './basemaps.js';
import { addLassoLayers, initLasso } from './lasso.js';
import { initPopup } from './popup.js';
import { initSearch } from './search.js';
import { siteUrl } from './paths.js';
import { redirectToSavedLanguage, initLanguageControl, initLanguageBanner } from './lang.js';

const ADDRESS_SOURCE = 'addresses-source';
const ADDRESS_TILES = siteUrl('addresses.pmtiles');

function customAttribution(i18n) {
  return [
    `${i18n.t('attribution.addresses')} <a href="https://datastore.brussels/web/data/dataset/a8c9ccde-5c2b-11ed-913a-900f0cda5d5c" target="_blank">Paradigm</a> (CC-0)`,
    '<a href="https://github.com/PasLoin/Urbis-BeSt-Address-Brussels-compare-OSM" target="_blank">PasLoin</a>'
  ];
}

function mapLocale(i18n) {
  return {
    'Map.Title': i18n.t('map.title'),
    'Popup.Close': i18n.t('map.closePopup'),
    'Marker.Title': i18n.t('search.marker'),
    'NavigationControl.ZoomIn': i18n.t('map.zoomIn'),
    'NavigationControl.ZoomOut': i18n.t('map.zoomOut'),
    'NavigationControl.ResetBearing': i18n.t('map.resetBearing'),
    'AttributionControl.ToggleAttribution': i18n.t('map.toggleAttribution')
  };
}

function loadVersion(i18n) {
  fetch(siteUrl('version.json'))
    .then(r => r.json())
    .then(version => {
      renderVersionInfo(version, i18n);
      renderStats(version, i18n);
    })
    .catch(() => renderVersionInfo(null, i18n));
}

function start(i18n) {
  loadVersion(i18n);

  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  protocol.add(new pmtiles.PMTiles(ADDRESS_TILES));

  const map = new maplibregl.Map({
    container: 'map',
    attributionControl: false,
    style: OSM_CARTO_STYLE,
    center: [4.352, 50.846],
    zoom: 10,
    maxZoom: 19,
    hash: true,
    locale: mapLocale(i18n)
  });
  const canvas = map.getCanvas();
  canvas.setAttribute('aria-describedby', 'map-help');

  let attributionControl = null;

  function renderAttribution() {
    if (attributionControl) map.removeControl(attributionControl);
    attributionControl = new maplibregl.AttributionControl({ compact: false, customAttribution: customAttribution(i18n) });
    map.addControl(attributionControl);
  }

  renderAttribution();
  map.addControl(new maplibregl.NavigationControl(), 'bottom-left');

  const filters = initFilters(map, { i18n });

  map.on('load', () => {
    map.addSource(ADDRESS_SOURCE, { type: 'vector', url: `pmtiles://${ADDRESS_TILES}` });
    map.addLayer({
      id: ADDRESS_LAYER,
      type: 'circle',
      source: ADDRESS_SOURCE,
      'source-layer': 'addresses',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 15, 4, 19, 8],
        'circle-color': statusColorExpression(),
        'circle-stroke-width': 1,
        'circle-stroke-color': '#fff'
      }
    });
    filters.apply();
    addLassoLayers(map);
  });

  const basemaps = initBasemaps(map, i18n);
  const lasso = initLasso(map, i18n);
  const popup = initPopup(map, { isLassoActive: lasso.isActive, i18n });
  const search = initSearch(map, { isLassoActive: lasso.isActive, i18n });
  const language = initLanguageControl(i18n);
  initLanguageBanner(i18n);

  canvas.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    if (lasso.isActive()) lasso.selectView();
    else popup.openNearestToCenter();
  });

  const escapeHandlers = [popup.close, language.handleEscape, basemaps.handleEscape, lasso.handleEscape, search.handleEscape];
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    escapeHandlers.some(handle => handle());
  });
}

const i18n = i18nFromDocument();
setI18n(i18n);
if (!redirectToSavedLanguage(i18n)) start(i18n);
