import { getI18n } from './i18n.js';

export const STATUSES = [
  { code: 'ok', color: '#2ecc71', labelKey: 'status.ok', statsKey: 'stats.ok', barKey: 'bar.ok', visibleByDefault: false, exportable: true, coverage: true },
  { code: 'missing', color: '#e74c3c', labelKey: 'status.missing', statsKey: 'stats.missing', barKey: 'bar.missing', visibleByDefault: true, exportable: true, coverage: true },
  { code: 'verified_absent', color: '#3498db', labelKey: 'status.verified_absent', statsKey: 'stats.verified_absent', barKey: 'bar.verified_absent', visibleByDefault: false, exportable: true, coverage: true },
  { code: 'missing_in_urbis', color: '#ff7000', labelKey: 'status.missing_in_urbis', statsKey: 'stats.missing_in_urbis', barKey: null, visibleByDefault: false, exportable: false, coverage: false },
  { code: 'missing_in_urbis_verified', color: '#ffc800', labelKey: 'status.missing_in_urbis_verified', statsKey: 'stats.missing_in_urbis_verified', barKey: null, visibleByDefault: false, exportable: false, coverage: false }
];

export const FALLBACK_STATUS = 'missing';

export const BAR_ORDER = ['ok', 'verified_absent', 'missing'];

export const NON_EXPORTABLE = new Set(STATUSES.filter(s => !s.exportable).map(s => s.code));

export function getStatus(code) {
  return STATUSES.find(s => s.code === code) || null;
}

export function statusLabel(code, i18n = getI18n()) {
  const status = getStatus(code);
  return status ? i18n.t(status.labelKey) : String(code);
}

export function statusColorExpression() {
  const pairs = STATUSES
    .filter(s => s.code !== FALLBACK_STATUS)
    .flatMap(s => [s.code, s.color]);
  return ['match', ['get', 'status'], ...pairs, getStatus(FALLBACK_STATUS).color];
}

export function statusDot(code) {
  const status = getStatus(code);
  return status ? `<span class="dot" style="background:${status.color}"></span>` : '';
}
