import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalize, fuzzyScore, splitQuery, highlight, searchIndex } from '../../js/search-match.js';
import { buildUrbisUrl, parsePosition } from '../../js/search.js';
import { pointInPolygon } from '../../js/geometry.js';
import { localStreet, localMunicipality, pickName } from '../../js/data-lang.js';

const INDEX = {
  s: ['Rue de la Loi - Wetstraat', 'Rue Royale - Koningsstraat', 'Avenue Louise - Louizalaan'],
  sn: ['rue de la loi - wetstraat', 'rue royale - koningsstraat', 'avenue louise - louizalaan'],
  a: [
    [0, '16', 50.8466, 4.3685],
    [0, '18', 50.8467, 4.3689],
    [1, '80', 50.8501, 4.3612],
    [1, '8', 50.8470, 4.3600],
    [2, '1', 50.8400, 4.3550]
  ]
};

test('normalize retire accents, casse et espaces multiples', () => {
  assert.equal(normalize('  Ch\u00e2teau   d\u2019EAU '), 'chateau d\u2019eau');
});

test('fuzzyScore classe exact, pr\u00e9fixe, contenu et mots', () => {
  assert.equal(fuzzyScore('rue royale', 'Rue Royale'), 100);
  assert.equal(fuzzyScore('rue roy', 'Rue Royale'), 90);
  assert.equal(fuzzyScore('royale', 'Rue Royale'), 70);
  assert.equal(fuzzyScore('royale rue', 'Rue Royale'), 60);
  assert.equal(fuzzyScore('xyz', 'Rue Royale'), 0);
});

test('splitQuery s\u00e9pare rue et num\u00e9ro', () => {
  assert.deepEqual(splitQuery('Rue Royale 80'), { street: 'Rue Royale', number: '80' });
  assert.deepEqual(splitQuery('Rue Royale, 12b'), { street: 'Rue Royale', number: '12b' });
  assert.deepEqual(splitQuery('Rue Royale'), { street: 'Rue Royale', number: null });
});

test('highlight \u00e9chappe le HTML', () => {
  assert.equal(highlight('<b>Loi</b>', 'zzz'), '&lt;b&gt;Loi&lt;/b&gt;');
  assert.equal(highlight('Rue de la Loi', 'loi'), 'Rue de la <span class="sr-hl">Loi</span>');
});

test('searchIndex trouve une rue puis une adresse', () => {
  const streets = searchIndex(INDEX, 'rue roy', 7);
  assert.equal(streets[0].label, 'Rue Royale - Koningsstraat');
  assert.deepEqual(streets[0].lngLat, [4.3612, 50.8501]);
  const addresses = searchIndex(INDEX, 'Rue Royale 8', 7);
  assert.deepEqual(addresses.map(r => r.label), ['Rue Royale - Koningsstraat 8', 'Rue Royale - Koningsstraat 80']);
  assert.deepEqual(searchIndex(INDEX, 'introuvable', 7), []);
});

test('buildUrbisUrl choisit le bon endpoint et garde la langue fr', () => {
  const street = buildUrbisUrl('Rue Royale', 'fr');
  assert.match(street.pathname, /searchStreetName$/);
  assert.equal(street.searchParams.get('searchLanguage'), 'fr');
  assert.equal(street.searchParams.get('policeNumber'), null);
  const address = buildUrbisUrl('Rue Royale 80', 'fr');
  assert.match(address.pathname, /searchAddress$/);
  assert.equal(address.searchParams.get('streetName'), 'Rue Royale');
  assert.equal(address.searchParams.get('policeNumber'), '80');
  assert.equal(buildUrbisUrl('Rue Royale', 'nl').searchParams.get('searchLanguage'), 'nl');
});

test('parsePosition lit les deux formats de coordonn\u00e9es', () => {
  assert.deepEqual(parsePosition({ position: { pointGeometry: { point: { pos: '149000.5 170000.25' } } } }), { x: 149000.5, y: 170000.25 });
  assert.deepEqual(parsePosition({ position: { pointGeometry: { point: { pos: ['1', '2'] } } } }), { x: 1, y: 2 });
  assert.equal(parsePosition({}), null);
});

test('pointInPolygon distingue int\u00e9rieur et ext\u00e9rieur', () => {
  const square = [[0, 0], [10, 0], [10, 10], [0, 10]];
  assert.ok(pointInPolygon([5, 5], square));
  assert.ok(!pointInPolygon([15, 5], square));
});

test('localStreet et localMunicipality respectent la langue et retombent sur le fran\u00e7ais', () => {
  const props = { STRNAMEFRE: 'Rue de la Loi', STRNAMEDUT: 'Wetstraat', MUNNAMEFRE: 'Bruxelles', MUNNAMEDUT: 'Brussel' };
  assert.deepEqual(localStreet(props, 'fr'), { primary: 'Rue de la Loi', secondary: 'Wetstraat' });
  assert.deepEqual(localStreet(props, 'nl'), { primary: 'Wetstraat', secondary: 'Rue de la Loi' });
  assert.equal(localMunicipality(props, 'fr'), 'Bruxelles');
  assert.equal(localMunicipality(props, 'nl'), 'Brussel');
  const osmOnly = { STRNAMEFRE: 'Rue X - X-straat', STRNAMEDUT: null, MUNNAMEDUT: null };
  assert.deepEqual(localStreet(osmOnly, 'nl'), { primary: 'Rue X - X-straat', secondary: '' });
  assert.equal(localMunicipality(osmOnly, 'nl'), '');
});

test('pickName pr\u00e9f\u00e8re la langue demand\u00e9e', () => {
  const names = [{ language: 'nl', spelling: 'Wetstraat' }, { language: 'fr', spelling: 'Rue de la Loi' }];
  assert.equal(pickName(names, 'fr'), 'Rue de la Loi');
  assert.equal(pickName(names, 'nl'), 'Wetstraat');
  assert.equal(pickName(names, 'de'), 'Wetstraat');
  assert.equal(pickName(undefined, 'fr'), '');
});
