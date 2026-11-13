import { getStatus, statusDot, statusLabel } from './statuses.js';
import { getI18n } from './i18n.js';
import { localizedDatabrusselsUrl } from './databrussels.js';
import { extractInspireId, inspireUrl, downloadOsmXml } from './osm-export.js';
import { localStreet, localMunicipality } from './data-lang.js';
import { escapeHtml } from './html.js';
import { showToast } from './toast.js';
import { announce } from './announce.js';
import { ADDRESS_LAYER } from './filters.js';

const BBOX_DELTA = 0.0008;

export function statusLabelHtml(code, i18n = getI18n()) {
  return getStatus(code) ? `${statusDot(code)}${escapeHtml(statusLabel(code, i18n))}` : escapeHtml(code);
}

export function externalLinks(lng, lat) {
  return {
    mapillary: `https://www.mapillary.com/app/?lat=${lat}&lng=${lng}&z=18&focus=map&mapStyle=OpenStreetMap&panos=true`,
    panoramax: `https://api.panoramax.xyz/?focus=map&map=18.12/${lat}/${lng}`,
    josm: `http://127.0.0.1:8111/load_and_zoom?left=${lng - BBOX_DELTA}&right=${lng + BBOX_DELTA}&top=${lat + BBOX_DELTA}&bottom=${lat - BBOX_DELTA}`
  };
}

export function popupHtml(props, lng, lat, uid, i18n = getI18n()) {
  const numericId = extractInspireId(props.INSPIRE_ID);
  const hasInspire = Boolean(props.INSPIRE_ID);
  const links = externalLinks(lng, lat);
  const street = localStreet(props, i18n.dataLang);
  const number = props.POLICENUM || '';
  const inspireRow = hasInspire
    ? `<div class="popup-meta-row"><strong>${escapeHtml(i18n.t('popup.inspire'))}</strong>
           <a href="${escapeHtml(localizedDatabrusselsUrl(inspireUrl(props.INSPIRE_ID), i18n.lang))}" target="_blank" rel="noopener noreferrer" class="inspire-link">${escapeHtml(numericId)}</a>
           <button type="button" class="copy-id-btn" id="${uid}" title="${escapeHtml(i18n.t('popup.copyId'))}">
             <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
             ${escapeHtml(i18n.t('popup.copy'))}
           </button></div>`
    : '';
  const osmButton = hasInspire ? `<button type="button" class="osm-xml-btn" id="osm-dl-${uid}" aria-label="${escapeHtml(i18n.t('lasso.export'))}"><span aria-hidden="true">⬇</span> .osm</button>` : '';
  return `<div class="popup-content">
          <div class="popup-title"><strong>${escapeHtml(street.primary)} ${escapeHtml(number)}</strong><br>
            <small>${escapeHtml(street.secondary)} ${street.secondary ? escapeHtml(number) : ''}</small></div>
          <div class="popup-meta">
            <div class="popup-meta-row"><strong>${escapeHtml(i18n.t('popup.status'))}</strong> ${statusLabelHtml(props.status, i18n)}</div>${inspireRow}</div>
          <div class="popup-footer">${escapeHtml(props.ZIPCODE || '')} ${escapeHtml(localMunicipality(props, i18n.dataLang))}</div>
          <div class="popup-links">
            <a href="${links.mapillary}" target="_blank" rel="noopener noreferrer">Mapillary</a>
            <a href="${links.panoramax}" target="_blank" rel="noopener noreferrer">Panoramax</a>
            <a href="${links.josm}" target="_blank" rel="noopener noreferrer">JOSM</a>
            ${osmButton}</div></div>`;
}

export function nearestFeature(features, project, center) {
  let best = null;
  for (const feature of features) {
    const [lng, lat] = feature.geometry.coordinates;
    const point = project([lng, lat]);
    const distance = (point.x - center.x) ** 2 + (point.y - center.y) ** 2;
    if (!best || distance < best.distance) best = { feature, lng, lat, distance };
  }
  return best;
}

export function initPopup(map, { isLassoActive, i18n = getI18n() }) {
  let current = null;

  function wireButtons(popup, props, lng, lat, uid) {
    if (!props.INSPIRE_ID) return;
    const root = popup.getElement();
    const numericId = extractInspireId(props.INSPIRE_ID);
    const copyButton = root.querySelector(`#${uid}`);
    if (copyButton) {
      copyButton.addEventListener('click', ev => {
        ev.stopPropagation();
        navigator.clipboard.writeText(numericId).then(() => showToast(i18n.t('toast.copied'), i18n));
      });
    }
    const downloadButton = root.querySelector(`#osm-dl-${uid}`);
    if (downloadButton) {
      downloadButton.addEventListener('click', ev => {
        ev.stopPropagation();
        downloadOsmXml([{ properties: props, lng, lat }], `address-${numericId}.osm`);
      });
    }
  }

  function open(props, lngLat) {
    const { lng, lat } = lngLat;
    const uid = 'copy-' + Date.now();
    if (current) current.remove();
    const popup = new maplibregl.Popup()
      .setLngLat(lngLat)
      .setHTML(popupHtml(props, lng, lat, uid, i18n))
      .addTo(map);
    current = popup;
    popup.on('close', () => {
      if (current === popup) current = null;
      const active = document.activeElement;
      if (!active || active === document.body) map.getCanvas().focus();
    });
    wireButtons(popup, props, lng, lat, uid);
    return popup;
  }

  function openNearestToCenter() {
    if (!map.getLayer(ADDRESS_LAYER)) return false;
    const canvas = map.getCanvas();
    const center = { x: canvas.clientWidth / 2, y: canvas.clientHeight / 2 };
    const features = map.queryRenderedFeatures({ layers: [ADDRESS_LAYER] });
    const best = nearestFeature(features, lngLat => map.project(lngLat), center);
    if (!best) {
      announce(i18n.t('map.noAddress'));
      return false;
    }
    open(best.feature.properties, { lng: best.lng, lat: best.lat });
    return true;
  }

  function close() {
    if (!current) return false;
    current.remove();
    return true;
  }

  map.on('click', ADDRESS_LAYER, e => {
    if (isLassoActive()) return;
    open(e.features[0].properties, e.lngLat);
  });
  map.on('mouseenter', ADDRESS_LAYER, () => { if (!isLassoActive()) map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', ADDRESS_LAYER, () => { if (!isLassoActive()) map.getCanvas().style.cursor = ''; });

  return { open, openNearestToCenter, close };
}
