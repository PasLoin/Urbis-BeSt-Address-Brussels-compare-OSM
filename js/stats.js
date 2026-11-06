import { STATUSES, BAR_ORDER, getStatus } from './statuses.js';
import { formatDate, formatNumber, formatPercent } from './format.js';
import { escapeHtml } from './html.js';
import { getI18n } from './i18n.js';

export function renderVersionInfo(version, i18n = getI18n()) {
  const notAvailable = i18n.t('common.notAvailable');
  document.getElementById('urbis-date').textContent =
    formatDate(version && version.urbis_date, { i18n }) || notAvailable;
  document.getElementById('osm-date').textContent =
    formatDate(version && version.osm_date, { withTime: true, i18n }) || notAvailable;
}

export function hasStats(version) {
  const s = version && version.stats;
  return Boolean(s && s.total > 0 && s.osm_loaded !== false);
}

export function statsBarHtml(stats, i18n = getI18n()) {
  return BAR_ORDER.map(code => {
    const status = getStatus(code);
    const ratio = (stats[code] || 0) / stats.total;
    const width = (ratio * 100).toFixed(3);
    const title = i18n.t('stats.barTitle', { label: i18n.t(status.barKey), value: formatPercent(ratio, i18n) });
    return `<span class="bar-seg" style="width:${width}%;background:${status.color}" title="${escapeHtml(title)}"></span>`;
  }).join('');
}

export function statsRowsHtml(stats, i18n = getI18n()) {
  const dot = color => `<span class="dot" style="background:${color}"></span>`;
  const rows = [
    `<div class="stats-row"><span>${escapeHtml(i18n.t('stats.total'))}</span><strong>${formatNumber(stats.total, i18n)}</strong></div>`
  ];
  for (const status of STATUSES.filter(s => s.coverage)) {
    const count = stats[status.code] || 0;
    rows.push(
      `<div class="stats-row">${dot(status.color)}<span>${escapeHtml(i18n.t(status.statsKey))}</span>` +
      `<span>${formatNumber(count, i18n)} (${formatPercent(count / stats.total, i18n)})</span></div>`
    );
  }
  const outside = STATUSES.filter(s => !s.coverage);
  const outsideTotal = outside.reduce((sum, s) => sum + (stats[s.code] || 0), 0);
  if (outsideTotal > 0) {
    outside.forEach((status, i) => {
      const cls = i === 0 ? 'stats-row stats-separator' : 'stats-row';
      rows.push(
        `<div class="${cls}">${dot(status.color)}<span>${escapeHtml(i18n.t(status.statsKey))}</span>` +
        `<span>${formatNumber(stats[status.code] || 0, i18n)}</span></div>`
      );
    });
  }
  return rows.join('');
}

export function renderStats(version, i18n = getI18n()) {
  if (!hasStats(version)) return;
  document.getElementById('stats-bar').innerHTML = statsBarHtml(version.stats, i18n);
  document.getElementById('stats-rows').innerHTML = statsRowsHtml(version.stats, i18n);
}
