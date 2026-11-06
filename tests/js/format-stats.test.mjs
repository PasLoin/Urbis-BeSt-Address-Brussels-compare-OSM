import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatNumber, formatPercent, formatDate } from '../../js/format.js';
import { hasStats, statsBarHtml, statsRowsHtml } from '../../js/stats.js';
import { i18nFor } from './helpers.mjs';

const FR = i18nFor('fr');
const EN = i18nFor('en');
const NL = i18nFor('nl');

const digits = s => s.replace(/\s/g, ' ');

const SAMPLE = {
  urbis_date: '2026-10-03',
  osm_date: '2026-11-03T07:08:34Z',
  stats: {
    total: 226680,
    ok: 224814,
    missing: 840,
    verified_absent: 1026,
    missing_in_urbis: 2495,
    missing_in_urbis_verified: 160,
    osm_loaded: true
  }
};

test('les nombres suivent la locale fr-BE', () => {
  assert.equal(digits(formatNumber(226680, FR)), '226 680');
});

test('les pourcentages utilisent la virgule d\u00e9cimale et trois d\u00e9cimales', () => {
  assert.equal(digits(formatPercent(0.99176, FR)), '99,176 %');
  assert.equal(digits(formatPercent(840 / 226680, FR)), '0,371 %');
});

test('les dates sont format\u00e9es en fuseau Europe/Brussels', () => {
  assert.equal(formatDate('2026-10-03', { i18n: FR }), '3 octobre 2026');
  assert.match(formatDate('2026-11-03T07:08:34Z', { withTime: true, i18n: FR }), /^3 novembre 2026.*08:08$/);
  assert.equal(formatDate('pas une date', { i18n: FR }), 'pas une date');
  assert.equal(formatDate(null, { i18n: FR }), null);
});

test('hasStats refuse les statistiques absentes ou sans OSM', () => {
  assert.ok(hasStats(SAMPLE));
  assert.ok(!hasStats({ stats: { ...SAMPLE.stats, osm_loaded: false } }));
  assert.ok(!hasStats({ stats: { total: 0 } }));
  assert.ok(!hasStats(null));
});

test('la barre suit l\u2019ordre pr\u00e9sentes, v\u00e9rifi\u00e9es absentes, manquantes', () => {
  const html = statsBarHtml(SAMPLE.stats, FR);
  const colors = [...html.matchAll(/background:(#[0-9a-f]{6})/g)].map(m => m[1]);
  assert.deepEqual(colors, ['#2ecc71', '#3498db', '#e74c3c']);
  assert.match(html, /width:99\.177%/);
  assert.match(digits(html), /title="Pr\u00e9sentes : 99,177 %"/);
});

test('les lignes de statistiques reprennent les libell\u00e9s et compteurs', () => {
  const html = digits(statsRowsHtml(SAMPLE.stats, FR));
  assert.match(html, /<span>Total UrbIS<\/span><strong>226 680<\/strong>/);
  assert.match(html, /Manquantes<\/span><span>840 \(0,371 %\)/);
  assert.match(html, /stats-row stats-separator/);
  assert.match(html, /Abs\. UrbIS \(v\u00e9rifi\u00e9e\)<\/span><span>160</);
});

test('pas de section hors UrbIS quand ses compteurs sont nuls', () => {
  const html = statsRowsHtml({ ...SAMPLE.stats, missing_in_urbis: 0, missing_in_urbis_verified: 0 }, FR);
  assert.doesNotMatch(html, /stats-separator/);
});

test('en anglais, nombres, pourcentages et dates suivent en-GB', () => {
  assert.equal(formatNumber(226680, EN), '226,680');
  assert.equal(formatPercent(0.99176, EN), '99.176%');
  assert.equal(formatDate('2026-10-03', { i18n: EN }), '3 October 2026');
  assert.equal(formatDate('2026-11-03T07:08:34Z', { withTime: true, i18n: EN }), '3 November 2026 at 08:08');
});

test('en anglais, la barre et les lignes sont traduites', () => {
  assert.match(statsBarHtml(SAMPLE.stats, EN), /title="Present: 99\.177%"/);
  const html = statsRowsHtml(SAMPLE.stats, EN);
  assert.match(html, /<span>UrbIS total<\/span><strong>226,680<\/strong>/);
  assert.match(html, /Missing<\/span><span>840 \(0\.371%\)/);
  assert.match(html, /Not in UrbIS \(verified\)<\/span><span>160</);
});

test('en n\u00e9erlandais, nombres, pourcentages et dates suivent nl-BE', () => {
  assert.equal(formatNumber(226680, NL), '226.680');
  assert.equal(formatPercent(0.99177, NL), '99,177%');
  assert.equal(formatDate('2026-10-03', { i18n: NL }), '3 oktober 2026');
  assert.equal(formatDate('2026-11-03T07:08:34Z', { withTime: true, i18n: NL }), '3 november 2026 om 08:08');
});

test('en n\u00e9erlandais, la barre et les lignes sont traduites', () => {
  assert.match(statsBarHtml(SAMPLE.stats, NL), /title="Aanwezig: 99,177%"/);
  const html = statsRowsHtml(SAMPLE.stats, NL);
  assert.match(html, /<span>Totaal UrbIS<\/span><strong>226\.680<\/strong>/);
  assert.match(html, /Ontbrekend<\/span><span>840 \(0,371%\)/);
});
