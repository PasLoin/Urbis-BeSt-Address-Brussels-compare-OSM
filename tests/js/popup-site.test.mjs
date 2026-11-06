import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { popupHtml, statusLabelHtml } from '../../js/popup.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = path => readFileSync(join(ROOT, path), 'utf-8');

test('le popup affiche le statut traduit et les noms FR puis NL', () => {
  const html = popupHtml({
    STRNAMEFRE: 'Rue de la Loi',
    STRNAMEDUT: 'Wetstraat',
    POLICENUM: '16',
    ZIPCODE: '1000',
    MUNNAMEFRE: 'Bruxelles',
    INSPIRE_ID: 'X/1234567',
    status: 'missing'
  }, 4.3685, 50.8466, 'copy-1');
  assert.match(html, /<strong>Statut :<\/strong>/);
  assert.match(html, /Manquante dans OSM/);
  assert.match(html, /<strong>Rue de la Loi 16<\/strong><br>\s*<small>Wetstraat 16<\/small>/);
  assert.match(html, /1000 Bruxelles/);
  assert.match(html, /href="https:\/\/databrussels\.be\/id\/address\/1234567"/);
  assert.match(html, /id="osm-dl-copy-1"/);
});

test('le popup \u00e9chappe les noms venant d\u2019OSM', () => {
  const html = popupHtml({
    STRNAMEFRE: '<img src=x onerror=alert(1)>',
    POLICENUM: '1"><script>',
    status: 'missing_in_urbis'
  }, 4.35, 50.85, 'copy-2');
  assert.doesNotMatch(html, /<img src=x/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /osm-dl-copy-2/);
});

test('un statut inconnu est affich\u00e9 tel quel, \u00e9chapp\u00e9', () => {
  assert.equal(statusLabelHtml('<x>'), '&lt;x&gt;');
});

test('index.html charge le module principal et plus aucun script en ligne', () => {
  const html = read('index.html');
  assert.match(html, /<script type="module" src="js\/app\.js"><\/script>/);
  const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)([^>]*)>/g)].map(m => m[1]);
  assert.deepEqual(inline, [' type="application/ld+json"']);
  assert.doesNotMatch(html, /<style>/);
});

test('les d\u00e9pendances CDN sont \u00e9pingl\u00e9es sur une version exacte', () => {
  const html = read('index.html');
  const urls = [...html.matchAll(/https:\/\/unpkg\.com\/([^/"]+)\//g)].map(m => m[1]);
  assert.ok(urls.length >= 3);
  for (const pkg of urls) assert.match(pkg, /@\d+\.\d+\.\d+$/, pkg);
});

test('chaque id cherch\u00e9 par le JS existe dans index.html', () => {
  const html = read('index.html');
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
  for (const file of readdirSync(join(ROOT, 'js'))) {
    const source = read(join('js', file));
    for (const [, id] of source.matchAll(/getElementById\('([^']+)'\)/g)) {
      assert.ok(ids.has(id), `${file} cherche #${id}, absent de index.html`);
    }
  }
});

test('chaque import relatif pointe vers un fichier existant', () => {
  for (const file of readdirSync(join(ROOT, 'js'))) {
    const source = read(join('js', file));
    for (const [, target] of source.matchAll(/from '(\.\/[^']+)'/g)) {
      assert.ok(existsSync(join(ROOT, 'js', target)), `${file} importe ${target}`);
    }
  }
});
