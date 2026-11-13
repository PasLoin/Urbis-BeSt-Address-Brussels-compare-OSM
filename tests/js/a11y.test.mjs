import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nearestFeature, popupHtml } from '../../js/popup.js';
import { i18nFor } from './helpers.mjs';

const point = (lng, lat, id) => ({ geometry: { coordinates: [lng, lat] }, properties: { id } });
const identity = ([x, y]) => ({ x, y });

test('l\u2019adresse ouverte au clavier est la plus proche du centre', () => {
  const best = nearestFeature([point(0, 0, 'a'), point(48, 52, 'b'), point(100, 100, 'c')], identity, { x: 50, y: 50 });
  assert.equal(best.feature.properties.id, 'b');
  assert.equal(best.lng, 48);
  assert.equal(best.lat, 52);
});

test('sans adresse rendue, rien n\u2019est ouvert', () => {
  assert.equal(nearestFeature([], identity, { x: 0, y: 0 }), null);
});

test('les boutons du popup sont nomm\u00e9s et ne soumettent rien', () => {
  const html = popupHtml({
    STRNAMEFRE: 'Rue de la Loi', STRNAMEDUT: 'Wetstraat', POLICENUM: '16', ZIPCODE: '1000',
    MUNNAMEFRE: 'Bruxelles', MUNNAMEDUT: 'Brussel', INSPIRE_ID: 'https://databrussels.be/id/address/158114', status: 'missing'
  }, 4.3685, 50.8466, 'copy-1', i18nFor('fr'));
  const buttons = html.match(/<button\b[^>]*>/g);
  assert.equal(buttons.length, 2);
  for (const button of buttons) assert.match(button, /type="button"/);
  assert.match(html, /class="osm-xml-btn"[^>]*aria-label="Exporter \.osm"/);
  assert.match(html, /<span aria-hidden="true">\u2b07<\/span> \.osm/);
});
