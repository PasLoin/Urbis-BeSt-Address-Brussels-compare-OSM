import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { popupHtml, statusLabelHtml } from '../../js/popup.js';
import { ROOT, readText, i18nFor } from './helpers.mjs';

const FR = i18nFor('fr');
const EN = i18nFor('en');
const NL = i18nFor('nl');

const TEMPLATE = 'templates/index.html.j2';
const JS_DIR = fileURLToPath(new URL('js/', ROOT));

const ADDRESS = {
  STRNAMEFRE: 'Rue de la Loi',
  STRNAMEDUT: 'Wetstraat',
  POLICENUM: '16',
  ZIPCODE: '1000',
  MUNNAMEFRE: 'Bruxelles',
  MUNNAMEDUT: 'Brussel',
  INSPIRE_ID: 'https://databrussels.be/id/address/158114',
  status: 'missing'
};

test('le popup affiche le statut traduit et les noms FR puis NL', () => {
  const html = popupHtml(ADDRESS, 4.3685, 50.8466, 'copy-1', FR);
  assert.match(html, /<strong>Statut :<\/strong>/);
  assert.match(html, /Manquante dans OSM/);
  assert.match(html, /<strong>Rue de la Loi 16<\/strong><br>\s*<small>Wetstraat 16<\/small>/);
  assert.match(html, /1000 Bruxelles/);
  assert.match(html, /title="Copier l&#39;ID"/);
  assert.match(html, /href="https:\/\/databrussels\.be\/fr\/id\/address\/158114"/);
  assert.match(html, /id="osm-dl-copy-1"/);
});

test('en anglais, le popup est traduit et garde les noms FR puis NL', () => {
  const html = popupHtml(ADDRESS, 4.3685, 50.8466, 'copy-1', EN);
  assert.match(html, /<strong>Status:<\/strong>/);
  assert.match(html, /Missing from OSM/);
  assert.match(html, /<strong>INSPIRE:<\/strong>/);
  assert.match(html, /href="https:\/\/databrussels\.be\/en\/id\/address\/158114"/);
  assert.match(html, /<strong>Rue de la Loi 16<\/strong><br>\s*<small>Wetstraat 16<\/small>/);
  assert.match(html, /1000 Bruxelles/);
  assert.doesNotMatch(html, /Statut|copier/);
});

test('en n\u00e9erlandais, le popup met la rue et la commune en n\u00e9erlandais', () => {
  const html = popupHtml(ADDRESS, 4.3685, 50.8466, 'copy-1', NL);
  assert.match(html, /<strong>Status:<\/strong>/);
  assert.match(html, /Ontbreekt in OSM/);
  assert.match(html, /<strong>Wetstraat 16<\/strong><br>\s*<small>Rue de la Loi 16<\/small>/);
  assert.match(html, /1000 Brussel/);
  assert.match(html, /title="ID kopi\u00ebren"/);
  assert.match(html, /href="https:\/\/databrussels\.be\/nl\/id\/address\/158114"/);
  assert.match(html, /class="inspire-link">158114</);
});

test('en n\u00e9erlandais, une adresse OSM sans nom n\u00e9erlandais reste lisible', () => {
  const html = popupHtml({
    STRNAMEFRE: 'Rue X - X-straat',
    STRNAMEDUT: null,
    POLICENUM: '3',
    ZIPCODE: '1000',
    MUNNAMEFRE: 'Bruxelles',
    MUNNAMEDUT: null,
    status: 'missing_in_urbis'
  }, 4.35, 50.85, 'copy-3', NL);
  assert.match(html, /<strong>Rue X - X-straat 3<\/strong>/);
  assert.match(html, /1000 Bruxelles/);
});

test('le popup \u00e9chappe les noms venant d\u2019OSM', () => {
  const html = popupHtml({
    STRNAMEFRE: '<img src=x onerror=alert(1)>',
    POLICENUM: '1"><script>',
    status: 'missing_in_urbis'
  }, 4.35, 50.85, 'copy-2', FR);
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /osm-dl-copy-2/);
});

test('un statut inconnu est affich\u00e9 tel quel, \u00e9chapp\u00e9', () => {
  assert.equal(statusLabelHtml('<x>', FR), '&lt;x&gt;');
});

test('le template charge le module principal et seulement des donn\u00e9es en ligne', () => {
  const html = readText(TEMPLATE);
  assert.match(html, /<script type="module" src="\{\{ root \}\}js\/app\.js"><\/script>/);
  const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)([^>]*)>/g)].map(m => m[1].trim());
  assert.deepEqual(inline, [
    'type="application/ld+json"',
    'type="application/json" id="i18n-dict"',
    'type="application/json" id="i18n-banners"'
  ]);
  assert.doesNotMatch(html, /<style>/);
});

test('les d\u00e9pendances CDN sont \u00e9pingl\u00e9es sur une version exacte', () => {
  const html = readText(TEMPLATE);
  const urls = [...html.matchAll(/https:\/\/unpkg\.com\/([^/"]+)\//g)].map(m => m[1]);
  assert.ok(urls.length >= 3);
  for (const pkg of urls) assert.match(pkg, /@\d+\.\d+\.\d+$/, pkg);
});

test('chaque id cherch\u00e9 par le JS existe dans le template', () => {
  const html = readText(TEMPLATE);
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
  for (const file of readdirSync(JS_DIR)) {
    const source = readText(`js/${file}`);
    for (const [, id] of source.matchAll(/getElementById\('([^']+)'\)/g)) {
      assert.ok(ids.has(id), `${file} cherche #${id}, absent du template`);
    }
  }
});

test('chaque import relatif pointe vers un fichier existant', () => {
  for (const file of readdirSync(JS_DIR)) {
    const source = readText(`js/${file}`);
    for (const [, target] of source.matchAll(/from '(\.\/[^']+)'/g)) {
      assert.ok(existsSync(new URL(`js/${target}`, ROOT)), `${file} importe ${target}`);
    }
  }
});
