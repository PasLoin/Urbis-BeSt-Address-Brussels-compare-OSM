import { getStatus, statusDot, statusLabel } from './statuses.js';
import { t } from './i18n.js';
import { extractInspireId, inspireUrl, downloadOsmXml } from './osm-export.js';
import { localStreet, localMunicipality } from './data-lang.js';
import { escapeHtml } from './html.js';
import { showToast } from './toast.js';
import { ADDRESS_LAYER } from './filters.js';

const BBOX_DELTA = 0.0008;

export function statusLabelHtml(code) {
  return getStatus(code) ? `${statusDot(code)}${escapeHtml(statusLabel(code))}` : escapeHtml(code);
}

export function externalLinks(lng, lat) {
  return {
    mapillary: `https://www.mapillary.com/app/?lat=${lat}&lng=${lng}&z=18&focus=map&mapStyle=OpenStreetMap&panos=true`,
    panoramax: `https://api.panoramax.xyz/?focus=map&map=18.12/${lat}/${lng}`,
    josm: `http://127.0.0.1:8111/load_and_zoom?left=${lng - BBOX_DELTA}&right=${lng + BBOX_DELTA}&top=${lat + BBOX_DELTA}&bottom=${lat - BBOX_DELTA}`
  };
}

export function popupHtml(props, lng, lat, uid) {
  const numericId = extractInspireId(props.INSPIRE_ID);
  const hasInspire = Boolean(props.INSPIRE_ID);
  const links = externalLinks(lng, lat);
  const street = localStreet(props);
  const number = props.POLICENUM || '';
  const inspireRow = hasInspire
    ? `<div class="popup-meta-row"><strong>${escapeHtml(t('popup.inspire'))}</strong>
           <a href="${escapeHtml(inspireUrl(props.INSPIRE_ID))}" target="_blank" rel="noopener noreferrer" class="inspire-link">${escapeHtml(numericId)}</a>
           <button class="copy-id-btn" id="${uid}" title="${escapeHtml(t('popup.copyId'))}">
             <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
             ${escapeHtml(t('popup.copy'))}
           </button></div>`
    : '';
  const osmButton = hasInspire ? `<button class="osm-xml-btn" id="osm-dl-${uid}">⬇ .osm</button>` : '';
  return `<div class="popup-content">
          <div class="popup-title"><strong>${escapeHtml(street.primary)} ${escapeHtml(number)}</strong><br>
            <small>${escapeHtml(street.secondary)} ${street.secondary ? escapeHtml(number) : ''}</small></div>
          <div class="popup-meta">
            <div class="popup-meta-row"><strong>${escapeHtml(t('popup.status'))}</strong> ${statusLabelHtml(props.status)}</div>${inspireRow}</div>
          <div class="popup-footer">${escapeHtml(props.ZIPCODE || '')} ${escapeHtml(localMunicipality(props))}</div>
          <div class="popup-links">
            <a href="${links.mapillary}" target="_blank" rel="noopener noreferrer">Mapillary</a>
            <a href="${links.panoramax}" target="_blank" rel="noopener noreferrer">Panoramax</a>
            <a href="${links.josm}" target="_blank" rel="noopener noreferrer">JOSM</a>
            ${osmButton}</div></div>`;
}

export function initPopup(map, { isLassoActive }) {
  map.on('click', ADDRESS_LAYER, e => {
    if (isLassoActive()) return;
    const props = e.features[0].properties;
    const { lng, lat } = e.lngLat;
    const uid = 'copy-' + Date.now();
    new maplibregl.Popup()
      .setLngLat(e.lngLat)
      .setHTML(popupHtml(props, lng, lat, uid))
      .addTo(map);
    if (!props.INSPIRE_ID) return;
    const numericId = extractInspireId(props.INSPIRE_ID);
    setTimeout(() => {
      const copyButton = document.getElementById(uid);
      if (copyButton) {
        copyButton.addEventListener('click', ev => {
          ev.stopPropagation();
          navigator.clipboard.writeText(numericId).then(() => showToast(t('toast.copied')));
        });
      }
      const downloadButton = document.getElementById('osm-dl-' + uid);
      if (downloadButton) {
        downloadButton.addEventListener('click', ev => {
          ev.stopPropagation();
          downloadOsmXml([{ properties: props, lng, lat }], `address-${numericId}.osm`);
        });
      }
    }, 50);
  });
  map.on('mouseenter', ADDRESS_LAYER, () => { if (!isLassoActive()) map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', ADDRESS_LAYER, () => { if (!isLassoActive()) map.getCanvas().style.cursor = ''; });
}
