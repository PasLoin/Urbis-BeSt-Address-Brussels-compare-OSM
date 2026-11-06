import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatNumber, formatPercent, formatDate } from '../../js/format.js';
import { hasStats, statsBarHtml, statsRowsHtml } from '../../js/stats.js';
import { useLang } from './helpers.mjs';

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
  useLang('fr');
  assert.equal(digits(formatNumber(226680)), '226 680');
});

test('les pourcentages utilisent la virgule d\u00e9cimale et trois d\u00e9cimales', () => {
  useLang('fr');
  assert.equal(digits(formatPercent(0.99176)), '99,176 %');
  assert.equal(digits(formatPercent(840 / 226680)), '0,371 %');
});

test('les dates sont format\u00e9es en fuseau Europe/Brussels', () => {
  useLang('fr');
  assert.equal(formatDate('2026-10-03'), '3 octobre 2026');
  assert.match(formatDate('2026-11-03T07:08:34Z', { withTime: true }), /^3 novembre 2026.*08:08$/);
  assert.equal(formatDate('pas une date'), 'pas une date');
  assert.equal(formatDate(null), null);
});

test('hasStats refuse les statistiques absentes ou sans OSM', () => {
  assert.ok(hasStats(SAMPLE));
  assert.ok(!hasStats({ stats: { ...SAMPLE.stats, osm_loaded: false } }));
  assert.ok(!hasStats({ stats: { total: 0 } }));
  assert.ok(!hasStats(null));
});

test('la barre suit l\u2019ordre pr\u00e9sentes, v\u00e9rifi\u00e9es absentes, manquantes', () => {
  useLang('fr');
  const html = statsBarHtml(SAMPLE.stats);
  const colors = [...html.matchAll(/background:(#[0-9a-f]{6})/g)].map(m => m[1]);
  assert.deepEqual(colors, ['#2ecc71', '#3498db', '#e74c3c']);
  assert.match(html, /width:99\.177%/);
  assert.match(digits(html), /title="Pr\u00e9sentes : 99,177 %"/);
});

test('les lignes de statistiques reprennent les libell\u00e9s et compteurs', () => {
  useLang('fr');
  const html = digits(statsRowsHtml(SAMPLE.stats));
  assert.match(html, /<span>Total UrbIS<\/span><strong>226 680<\/strong>/);
  assert.match(html, /Manquantes<\/span><span>840 \(0,371 %\)/);
  assert.match(html, /stats-row stats-separator/);
  assert.match(html, /Abs\. UrbIS \(v\u00e9rifi\u00e9e\)<\/span><span>160</);
});

test('pas de section hors UrbIS quand ses compteurs sont nuls', () => {
  const html = statsRowsHtml({ ...SAMPLE.stats, missing_in_urbis: 0, missing_in_urbis_verified: 0 });
  assert.doesNotMatch(html, /stats-separator/);
});

test('en anglais, nombres, pourcentages et dates suivent en-GB', () => {
  useLang('en');
  assert.equal(formatNumber(226680), '226,680');
  assert.equal(formatPercent(0.99176), '99.176%');
  assert.equal(formatDate('2026-10-03'), '3 October 2026');
  assert.equal(formatDate('2026-11-03T07:08:34Z', { withTime: true }), '3 November 2026 at 08:08');
});

test('en anglais, la barre et les lignes sont traduites', () => {
  useLang('en');
  assert.match(statsBarHtml(SAMPLE.stats), /title="Present: 99\.177%"/);
  const html = statsRowsHtml(SAMPLE.stats);
  assert.match(html, /<span>UrbIS total<\/span><strong>226,680<\/strong>/);
  assert.match(html, /Missing<\/span><span>840 \(0\.371%\)/);
  assert.match(html, /Not in UrbIS \(verified\)<\/span><span>160</);
});
