import { i18nFromDocument, setI18n, t } from './i18n.js';
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

function customAttribution() {
  return [
    `${t('attribution.addresses')} <a href="https://datastore.brussels/web/data/dataset/a8c9ccde-5c2b-11ed-913a-900f0cda5d5c" target="_blank">Paradigm</a> (CC-0)`,
    '<a href="https://github.com/PasLoin/Urbis-BeSt-Address-Brussels-compare-OSM" target="_blank">PasLoin</a>'
  ];
}

function loadVersion() {
  fetch(siteUrl('version.json'))
    .then(r => r.json())
    .then(version => {
      renderVersionInfo(version);
      renderStats(version);
    })
    .catch(() => renderVersionInfo(null));
}

function start() {
  loadVersion();

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
    hash: true
  });

  let attributionControl = null;

  function renderAttribution() {
    if (attributionControl) map.removeControl(attributionControl);
    attributionControl = new maplibregl.AttributionControl({ compact: false, customAttribution: customAttribution() });
    map.addControl(attributionControl);
  }

  renderAttribution();
  map.addControl(new maplibregl.NavigationControl(), 'bottom-left');

  const filters = initFilters(map);

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

  initBasemaps(map);
  const lasso = initLasso(map);
  initPopup(map, { isLassoActive: lasso.isActive });
  const search = initSearch(map, { isLassoActive: lasso.isActive });
  initLanguageControl();
  initLanguageBanner();

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (lasso.handleEscape()) return;
    search.handleEscape();
  });
}

setI18n(i18nFromDocument());
if (!redirectToSavedLanguage()) start();
