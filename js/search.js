import { escapeHtml } from './html.js';
import { fuzzyScore, highlight, searchIndex, splitQuery } from './search-match.js';
import { pickName } from './data-lang.js';
import { getI18n } from './i18n.js';
import { DATABRUSSELS_HOST, localizedDatabrusselsUrl } from './databrussels.js';
import { siteUrl } from './paths.js';
import { announce } from './announce.js';

const URBIS_LANGS = ['fr', 'nl'];
const URBIS_BASE = 'https://geoservices.irisnet.be/geocoding/api/v1/brussels/geocoding';
const SEARCH_MAX = 7;
const SEARCH_ZOOM = 18;
const PROJ4_URL = 'https://cdnjs.cloudflare.com/ajax/libs/proj4js/2.11.0/proj4.min.js';
const PROJ_L72 = '+proj=lcc +lat_1=51.16666723333333 +lat_2=49.8333339 '
  + '+lat_0=90 +lon_0=4.367486666666666 +x_0=150000.013 '
  + '+y_0=5400088.438 +ellps=intl '
  + '+towgs84=-106.869,52.2978,-103.724,0.3366,-0.457,1.8422,-1.2747 '
  + '+units=m +no_defs';

let proj4Promise = null;

function ensureProj4(i18n) {
  if (!proj4Promise) {
    proj4Promise = new Promise((ok, fail) => {
      if (window.proj4) { ok(); return; }
      const s = document.createElement('script');
      s.src = PROJ4_URL;
      s.onload = ok;
      s.onerror = () => fail(new Error(i18n.t('search.proj4Unavailable')));
      document.head.appendChild(s);
    });
  }
  return proj4Promise;
}

async function lambertToLngLat(x, y, i18n) {
  await ensureProj4(i18n);
  if (!window.proj4.defs('EPSG:31370')) window.proj4.defs('EPSG:31370', PROJ_L72);
  const [lon, lat] = window.proj4('EPSG:31370', 'WGS84', [+x, +y]);
  return [lon, lat];
}

export function parsePosition(obj) {
  const posStr = obj?.position?.pointGeometry?.point?.pos;
  if (typeof posStr === 'string') {
    const parts = posStr.trim().split(/\s+/);
    if (parts.length >= 2) {
      const x = parseFloat(parts[0]);
      const y = parseFloat(parts[1]);
      if (!isNaN(x) && !isNaN(y)) return { x, y };
    }
  }
  if (Array.isArray(posStr) && posStr.length >= 2) {
    return { x: parseFloat(posStr[0]), y: parseFloat(posStr[1]) };
  }
  return null;
}

export function buildUrbisUrl(query, lang = getI18n().dataLang) {
  const { street, number } = splitQuery(query);
  const url = new URL(`${URBIS_BASE}/${number ? 'searchAddress' : 'searchStreetName'}`);
  url.searchParams.set('searchLanguage', lang);
  url.searchParams.set('streetName', street.trim());
  if (number) url.searchParams.set('policeNumber', number);
  url.searchParams.set('model', 'BeStPlus');
  return url;
}

export function streetNameUrl(streetName, lang = getI18n().lang) {
  const code = streetName?.code;
  let url = streetName?.href || null;
  if (!url && code?.objectIdentifier) {
    url = `https://${DATABRUSSELS_HOST}/id/streetname/${code.objectIdentifier}`;
    if (code.versionIdentifier) url += `/${code.versionIdentifier}`;
  }
  return localizedDatabrusselsUrl(url, lang);
}

export function urbisLanguages(primary = getI18n().dataLang) {
  return [primary, ...URBIS_LANGS.filter(lang => lang !== primary)];
}

export async function searchAcrossLanguages(langs, searchIn) {
  let answered = false;
  let lastError = null;
  for (const lang of langs) {
    try {
      const results = await searchIn(lang);
      answered = true;
      if (results.length) return results;
    } catch (e) {
      lastError = e;
    }
  }
  if (!answered && lastError) throw lastError;
  return [];
}

function searchUrbis(query, maxResults, i18n) {
  return searchAcrossLanguages(urbisLanguages(i18n.dataLang), lang => searchUrbisIn(query, lang, maxResults, i18n));
}

async function searchUrbisIn(query, lang, maxResults, i18n) {
  const url = buildUrbisUrl(query, lang);
  let resp;
  try {
    resp = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch (netErr) {
    throw new Error(i18n.t('search.networkError', { message: netErr.message }));
  }
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`UrbIS HTTP ${resp.status} \u2014 ${body.slice(0, 80)}`);
  }
  const data = await resp.json();
  const results = [];
  for (const group of (data.resultsList || [])) {
    for (const item of (group.result || [])) {
      let label = '';
      let sub = '';
      let pos = null;
      let refUrl = null;
      if (item.address) {
        const addr = item.address;
        label = pickName(addr.hasStreetName?.streetname?.name, i18n.dataLang);
        const hn = addr.houseNumber || '';
        if (hn) label = `${label} ${hn}`.trim();
        const mun = pickName(addr.hasMunicipality?.name, i18n.dataLang);
        const pc = addr.hasPostalInfo?.code?.objectIdentifier || '';
        sub = [mun, pc].filter(Boolean).join(' \u00b7 ');
        pos = parsePosition(addr);
      } else if (item.streetname) {
        const sn = item.streetname;
        label = pickName(sn?.name, i18n.dataLang);
        sub = pickName(item.municipality?.name, i18n.dataLang) || '';
        pos = parsePosition(sn) || parsePosition(item);
        refUrl = streetNameUrl(sn, i18n.lang);
      } else if (item.municipality) {
        label = pickName(item.municipality.name, i18n.dataLang);
        pos = parsePosition(item.municipality);
      } else {
        continue;
      }
      if (!label || !pos) continue;
      try {
        const lngLat = await lambertToLngLat(pos.x, pos.y, i18n);
        results.push({ label, sub, lngLat, score: fuzzyScore(query, label), source: 'urbis', refUrl });
      } catch (_) {}
    }
  }
  return results.sort((a, b) => b.score - a.score).slice(0, maxResults);
}

export function initSearch(map, { isLassoActive, i18n = getI18n() }) {
  let source = 'osm';
  let index = null;
  let indexLoading = false;
  let indexCallbacks = [];
  let marker = null;
  let debounce = null;
  let activeItem = -1;
  let currentItems = [];
  const bar = document.getElementById('search-bar');
  const toggle = document.getElementById('search-toggle');
  const input = document.getElementById('search-input');
  const clear = document.getElementById('search-clear');
  const dropdown = document.getElementById('search-dropdown');
  const control = document.getElementById('search-control');

  function loadIndex() {
    return new Promise((ok, fail) => {
      if (index) { ok(index); return; }
      indexCallbacks.push({ ok, fail });
      if (indexLoading) return;
      indexLoading = true;
      fetch(siteUrl('search-index.json'))
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(data => { index = data; indexCallbacks.forEach(cb => cb.ok(data)); indexCallbacks = []; })
        .catch(err => { indexLoading = false; indexCallbacks.forEach(cb => cb.fail(err)); indexCallbacks = []; });
    });
  }

  function removeMarker() {
    if (marker) { marker.remove(); marker = null; }
  }

  function setOpen(open) {
    dropdown.classList.toggle('open', open);
    input.setAttribute('aria-expanded', open && currentItems.length ? 'true' : 'false');
  }

  function setActive(index) {
    activeItem = index;
    const options = dropdown.querySelectorAll('li[role="option"]');
    options.forEach((li, i) => {
      li.classList.toggle('active', i === index);
      li.setAttribute('aria-selected', i === index ? 'true' : 'false');
    });
    if (index >= 0 && options[index]) input.setAttribute('aria-activedescendant', options[index].id);
    else input.removeAttribute('aria-activedescendant');
  }

  function showStatus(msg, isError = false) {
    currentItems = [];
    dropdown.removeAttribute('role');
    input.removeAttribute('aria-activedescendant');
    dropdown.innerHTML = `<li class="${isError ? 'error-row' : 'status-row'}">${escapeHtml(msg)}</li>`;
    setOpen(true);
    announce(msg);
  }

  function hide() {
    setOpen(false);
    setActive(-1);
  }

  function render(items, query) {
    currentItems = items;
    dropdown.innerHTML = '';
    dropdown.setAttribute('role', 'listbox');
    items.forEach((r, i) => {
      const li = document.createElement('li');
      li.id = `search-option-${i}`;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', 'false');
      const badge = r.source === 'osm'
        ? '<span class="sr-badge osm">OSM</span>'
        : '<span class="sr-badge">UrbIS</span>';
      li.innerHTML = `<div class="sr-label">${highlight(r.label, query)}${badge}</div>`
        + (r.sub ? `<div class="sr-sub">${escapeHtml(r.sub)}</div>` : '');
      li.addEventListener('click', () => select(r));
      li.addEventListener('mouseenter', () => setActive(i));
      dropdown.appendChild(li);
    });
    setActive(-1);
    setOpen(true);
    announce(i18n.t('search.resultCount', { count: items.length }));
  }

  function moveActive(dir) {
    const lis = dropdown.querySelectorAll('li[role="option"]');
    if (!lis.length) return;
    setActive(Math.max(0, Math.min(lis.length - 1, activeItem + dir)));
    lis[activeItem]?.scrollIntoView({ block: 'nearest' });
  }

  function select(result) {
    input.value = result.label;
    clear.classList.add('visible');
    hide();
    const [lon, lat] = result.lngLat;
    removeMarker();
    const refLink = result.refUrl
      ? `<br><a class="search-popup-ref" href="${escapeHtml(result.refUrl)}" target="_blank" rel="noopener noreferrer">databrussels.be <span aria-hidden="true">↗</span></a>`
      : '';
    marker = new maplibregl.Marker({ color: '#e74c3c' })
      .setLngLat([lon, lat])
      .setPopup(new maplibregl.Popup({ offset: 28, maxWidth: '240px' })
        .setHTML(`<strong>${escapeHtml(result.label)}</strong>`
          + (result.sub ? `<br><span class="search-popup-sub">${escapeHtml(result.sub)}</span>` : '')
          + refLink))
      .addTo(map)
      .togglePopup();
    map.flyTo({ center: [lon, lat], zoom: SEARCH_ZOOM, duration: 600 });
  }

  async function search(query) {
    showStatus(i18n.t('search.searching'));
    try {
      if (source === 'osm') {
        await loadIndex();
        const results = searchIndex(index, query, SEARCH_MAX);
        if (!results.length) showStatus(i18n.t('search.noResultOsm'));
        else render(results, query);
      } else {
        const results = await searchUrbis(query, SEARCH_MAX, i18n);
        if (!results.length) showStatus(i18n.t('search.noResultUrbis'));
        else render(results, query);
      }
    } catch (e) {
      console.error('[Search]', e);
      showStatus(e.message || i18n.t('search.error'), true);
    }
  }

  function setExpanded(expanded) {
    bar.classList.toggle('expanded', expanded);
    toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }

  function collapse() {
    setExpanded(false);
    input.value = '';
    clear.classList.remove('visible');
    hide();
    removeMarker();
  }

  toggle.addEventListener('click', () => {
    if (bar.classList.contains('expanded')) {
      collapse();
    } else {
      setExpanded(true);
      input.focus();
    }
  });

  input.addEventListener('input', () => {
    const q = input.value.trim();
    clear.classList.toggle('visible', q.length > 0);
    hide();
    if (source === 'osm') {
      if (q.length < 3) return;
      clearTimeout(debounce);
      debounce = setTimeout(() => search(q), 320);
    } else if (q.length >= 3) {
      showStatus(i18n.t('search.pressEnter'));
    }
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      if (dropdown.classList.contains('open') && activeItem >= 0 && currentItems[activeItem]) {
        e.preventDefault();
        select(currentItems[activeItem]);
      } else if (source === 'urbis') {
        const q = input.value.trim();
        if (q.length >= 3) { e.preventDefault(); search(q); }
      }
      return;
    }
    if (!dropdown.classList.contains('open')) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); moveActive(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(-1); }
    else if (e.key === 'Tab') {
      if (activeItem >= 0 && currentItems[activeItem]) { e.preventDefault(); select(currentItems[activeItem]); }
    }
  });

  clear.addEventListener('click', () => {
    input.value = '';
    clear.classList.remove('visible');
    hide();
    removeMarker();
    input.focus();
  });

  document.querySelectorAll('.src-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      source = btn.dataset.src;
      document.querySelectorAll('.src-btn').forEach(b => {
        b.classList.toggle('active', b === btn);
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      hide();
      const q = input.value.trim();
      if (source === 'osm' && q.length >= 3) {
        search(q);
      } else if (source === 'urbis' && q.length >= 3) {
        showStatus(i18n.t('search.pressEnter'));
      }
      if (source === 'osm') loadIndex().catch(() => {});
    });
  });

  map.on('click', () => { if (!isLassoActive()) hide(); });
  control.addEventListener('focusout', e => {
    if (e.relatedTarget && !control.contains(e.relatedTarget)) hide();
  });
  toggle.addEventListener('mouseenter', () => loadIndex().catch(() => {}), { once: true });
  toggle.addEventListener('focus', () => loadIndex().catch(() => {}), { once: true });

  function handleEscape() {
    if (dropdown.classList.contains('open')) {
      hide();
      return true;
    }
    if (bar.classList.contains('expanded')) {
      const hadFocus = bar.contains(document.activeElement);
      collapse();
      if (hadFocus) toggle.focus();
      return true;
    }
    return false;
  }

  return { handleEscape };
}
