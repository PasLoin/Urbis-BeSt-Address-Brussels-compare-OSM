import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  extractInspireId,
  inspireUrl,
  buildStreetTag,
  escapeXml,
  generateOsmXml
} from '../../js/osm-export.js';

test('extractInspireId garde les chiffres finaux', () => {
  assert.equal(extractInspireId('BE.BRUSSELS.BRIC.ADM.ADDR/1234567'), '1234567');
  assert.equal(extractInspireId('abc'), 'abc');
  assert.equal(extractInspireId(null), null);
});

test('inspireUrl pointe vers databrussels.be', () => {
  assert.equal(inspireUrl('X/42'), 'https://databrussels.be/id/address/42');
  assert.equal(inspireUrl(''), null);
});

test('buildStreetTag combine FR et NL sans doublon', () => {
  assert.equal(buildStreetTag('Rue de la Loi', 'Wetstraat'), 'Rue de la Loi - Wetstraat');
  assert.equal(buildStreetTag('Avenue Louise', 'Avenue Louise'), 'Avenue Louise');
  assert.equal(buildStreetTag('', 'Wetstraat'), 'Wetstraat');
});

test('escapeXml échappe les cinq caractères réservés', () => {
  assert.equal(escapeXml(`<a & "b" 'c'>`), '&lt;a &amp; &quot;b&quot; &apos;c&apos;&gt;');
  assert.equal(escapeXml(null), '');
});

test('generateOsmXml produit exactement la sortie de référence', () => {
  const xml = generateOsmXml([
    {
      properties: {
        STRNAMEFRE: 'Rue de la Loi',
        STRNAMEDUT: 'Wetstraat',
        POLICENUM: '16',
        INSPIRE_ID: 'BE.BRUSSELS.BRIC.ADM.ADDR/1234567'
      },
      lng: 4.3685,
      lat: 50.8466
    },
    {
      properties: { STRNAMEFRE: "Rue d'Arlon", STRNAMEDUT: 'Aarlenstraat', POLICENUM: '2A' },
      geometry: { coordinates: [4.37, 50.84] }
    }
  ]);
  assert.equal(xml, [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<osm version="0.6" generator="UrbIS-Sync">',
    '  <node id="-1" lat="50.8466" lon="4.3685" version="0" changeset="0">',
    '    <tag k="addr:housenumber" v="16"/>',
    '    <tag k="addr:street" v="Rue de la Loi - Wetstraat"/>',
    '    <tag k="ref:databrussels" v="1234567"/>',
    '  </node>',
    '  <node id="-2" lat="50.84" lon="4.37" version="0" changeset="0">',
    '    <tag k="addr:housenumber" v="2A"/>',
    '    <tag k="addr:street" v="Rue d&apos;Arlon - Aarlenstraat"/>',
    '  </node>',
    '</osm>',
    ''
  ].join('\n'));
});
