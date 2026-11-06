import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  STATUSES,
  BAR_ORDER,
  NON_EXPORTABLE,
  getStatus,
  statusLabel,
  statusColorExpression,
  statusDot
} from '../../js/statuses.js';
import { initialFilterState, filterExpression } from '../../js/filters.js';
import { loadDict, useLang } from './helpers.mjs';

test('les codes de statut sont uniques et correspondent aux tuiles', () => {
  const codes = STATUSES.map(s => s.code);
  assert.deepEqual(codes, ['ok', 'missing', 'verified_absent', 'missing_in_urbis', 'missing_in_urbis_verified']);
  assert.equal(new Set(codes).size, codes.length);
});

test('statusColorExpression reproduit l\u2019expression MapLibre d\u2019origine', () => {
  assert.deepEqual(statusColorExpression(), [
    'match', ['get', 'status'],
    'ok', '#2ecc71',
    'verified_absent', '#3498db',
    'missing_in_urbis', '#ff7000',
    'missing_in_urbis_verified', '#ffc800',
    '#e74c3c'
  ]);
});

test('seules les adresses UrbIS sont exportables', () => {
  assert.deepEqual([...NON_EXPORTABLE].sort(), ['missing_in_urbis', 'missing_in_urbis_verified']);
});

test('la barre ne contient que des statuts de couverture', () => {
  for (const code of BAR_ORDER) {
    assert.ok(getStatus(code).coverage);
    assert.ok(getStatus(code).barKey);
  }
});

test('chaque cl\u00e9 de statut existe dans les dictionnaires', () => {
  for (const lang of ['fr', 'en']) {
    const dict = loadDict(lang);
    for (const status of STATUSES) {
      for (const key of [status.labelKey, status.statsKey, status.barKey].filter(Boolean)) {
        assert.ok(key in dict, `${lang}.json : ${key}`);
      }
    }
  }
});

test('statusLabel suit la langue courante', () => {
  useLang('fr');
  assert.equal(statusLabel('missing'), 'Manquante dans OSM');
  useLang('en');
  assert.equal(statusLabel('missing'), 'Missing from OSM');
  assert.equal(statusLabel('inconnu'), 'inconnu');
});

test('statusDot utilise la couleur du statut', () => {
  assert.equal(statusDot('ok'), '<span class="dot" style="background:#2ecc71"></span>');
  assert.equal(statusDot('inconnu'), '');
});

test('seul le statut missing est affich\u00e9 au d\u00e9part', () => {
  assert.deepEqual(initialFilterState(), {
    ok: false,
    missing: true,
    verified_absent: false,
    missing_in_urbis: false,
    missing_in_urbis_verified: false
  });
});

test('filterExpression couvre aucun, certains et tous les statuts', () => {
  const none = Object.fromEntries(STATUSES.map(s => [s.code, false]));
  const all = Object.fromEntries(STATUSES.map(s => [s.code, true]));
  assert.deepEqual(filterExpression(none), ['==', 'status', '__none__']);
  assert.equal(filterExpression(all), null);
  assert.deepEqual(filterExpression(initialFilterState()), ['in', ['get', 'status'], ['literal', ['missing']]]);
});
