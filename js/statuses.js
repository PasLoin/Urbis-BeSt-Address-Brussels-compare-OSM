export const STATUSES = [
  {
    code: 'ok',
    color: '#2ecc71',
    label: 'Présente dans OSM',
    statsLabel: 'Présentes',
    barLabel: 'Présentes',
    visibleByDefault: false,
    exportable: true,
    coverage: true
  },
  {
    code: 'missing',
    color: '#e74c3c',
    label: 'Manquante dans OSM',
    statsLabel: 'Manquantes',
    barLabel: 'Manquantes',
    visibleByDefault: true,
    exportable: true,
    coverage: true
  },
  {
    code: 'verified_absent',
    color: '#3498db',
    label: 'Vérifiée absente',
    statsLabel: 'Vérifiées abs.',
    barLabel: 'Vérifiées absentes',
    visibleByDefault: false,
    exportable: true,
    coverage: true
  },
  {
    code: 'missing_in_urbis',
    color: '#ff7000',
    label: "Absente d'UrbIS (à vérifier)",
    statsLabel: 'Abs. UrbIS (à vér.)',
    barLabel: null,
    visibleByDefault: false,
    exportable: false,
    coverage: false
  },
  {
    code: 'missing_in_urbis_verified',
    color: '#ffc800',
    label: "Absente d'UrbIS (vérifiée)",
    statsLabel: 'Abs. UrbIS (vérifiée)',
    barLabel: null,
    visibleByDefault: false,
    exportable: false,
    coverage: false
  }
];

export const FALLBACK_STATUS = 'missing';

export const BAR_ORDER = ['ok', 'verified_absent', 'missing'];

export const NON_EXPORTABLE = new Set(STATUSES.filter(s => !s.exportable).map(s => s.code));

export function getStatus(code) {
  return STATUSES.find(s => s.code === code) || null;
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
