import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createI18n, setI18n, t, currentLang, currentLocale } from '../../js/i18n.js';
import { suggestedLang, redirectTarget, primaryBrowserLang } from '../../js/lang.js';
import { generateOsmXml } from '../../js/osm-export.js';
import { dataLang, localStreet } from '../../js/data-lang.js';
import { buildUrbisUrl, urbisLanguages, searchAcrossLanguages, localizedDatabrusselsUrl, streetNameUrl } from '../../js/search.js';
import { useLang } from './helpers.mjs';

const DICT = {
  greeting: 'Bonjour {name}',
  items: { one: '{count} \u00e9l\u00e9ment', other: '{count} \u00e9l\u00e9ments' }
};

test('t remplace les variables et garde celles qui manquent', () => {
  const i18n = createI18n('fr', DICT);
  assert.equal(i18n.t('greeting', { name: 'Bruxelles' }), 'Bonjour Bruxelles');
  assert.equal(i18n.t('greeting'), 'Bonjour {name}');
});

test('une cl\u00e9 inconnue est rendue telle quelle', () => {
  assert.equal(createI18n('fr', DICT).t('absente'), 'absente');
});

test('les pluriels suivent les r\u00e8gles de chaque langue', () => {
  const fr = createI18n('fr', DICT);
  assert.equal(fr.t('items', { count: 0 }), '0 \u00e9l\u00e9ment');
  assert.equal(fr.t('items', { count: 1 }), '1 \u00e9l\u00e9ment');
  assert.equal(fr.t('items', { count: 2 }), '2 \u00e9l\u00e9ments');
  const en = createI18n('en', { items: { one: '{count} item', other: '{count} items' } });
  assert.equal(en.t('items', { count: 0 }), '0 items');
  assert.equal(en.t('items', { count: 1 }), '1 item');
});

test('la langue courante pilote t, la locale et la langue des donn\u00e9es', () => {
  setI18n(createI18n('en', { hello: 'Hello' }));
  assert.equal(t('hello'), 'Hello');
  assert.equal(currentLang(), 'en');
  assert.equal(currentLocale(), 'en-GB');
  assert.equal(dataLang(), 'fr');
  setI18n(createI18n('nl', {}));
  assert.equal(dataLang(), 'nl');
  assert.equal(currentLocale(), 'nl-BE');
  assert.deepEqual(localStreet({ STRNAMEFRE: 'Rue de la Loi', STRNAMEDUT: 'Wetstraat' }), { primary: 'Wetstraat', secondary: 'Rue de la Loi' });
  assert.equal(buildUrbisUrl('Wetstraat 16').searchParams.get('searchLanguage'), 'nl');
});

test('le pluriel du lasso existe en fran\u00e7ais et en anglais', () => {
  useLang('fr');
  assert.equal(t('lasso.selected', { count: 1 }), 'adresse s\u00e9lectionn\u00e9e');
  assert.equal(t('lasso.selected', { count: 3 }), 'adresses s\u00e9lectionn\u00e9es');
  useLang('en');
  assert.equal(t('lasso.selected', { count: 1 }), 'address selected');
  assert.equal(t('lasso.selected', { count: 0 }), 'addresses selected');
});

test('l\u2019export .osm est identique quelle que soit la langue', () => {
  const features = [{
    properties: { STRNAMEFRE: 'Rue de la Loi', STRNAMEDUT: 'Wetstraat', POLICENUM: '16', INSPIRE_ID: 'X/1' },
    lng: 4.3685,
    lat: 50.8466
  }];
  useLang('fr');
  const fr = generateOsmXml(features);
  useLang('en');
  assert.equal(generateOsmXml(features), fr);
});

test('seule la langue principale du navigateur d\u00e9clenche le bandeau', () => {
  const base = { pageLang: 'fr', available: ['fr', 'en'], savedChoice: null };
  assert.equal(suggestedLang({ ...base, browserLanguages: ['en-US', 'en'] }), 'en');
  assert.equal(suggestedLang({ ...base, browserLanguages: ['fr-BE', 'en'] }), null);
  assert.equal(suggestedLang({ ...base, browserLanguages: ['nl-BE', 'nl', 'en'] }), null);
  assert.equal(suggestedLang({ ...base, browserLanguages: ['en-GB'], savedChoice: 'fr' }), null);
  assert.equal(suggestedLang({ ...base, browserLanguages: [] }), null);
  assert.equal(primaryBrowserLang(['NL-be']), 'nl');
});

test('la redirection n\u2019a lieu que depuis la racine et sur choix m\u00e9moris\u00e9', () => {
  const base = { pageLang: 'fr', available: ['fr', 'en'] };
  assert.equal(redirectTarget({ ...base, isRoot: true, savedChoice: 'en' }), 'en');
  assert.equal(redirectTarget({ ...base, isRoot: true, savedChoice: 'fr' }), null);
  assert.equal(redirectTarget({ ...base, isRoot: true, savedChoice: null }), null);
  assert.equal(redirectTarget({ ...base, isRoot: true, savedChoice: 'nl' }), null);
  assert.equal(redirectTarget({ pageLang: 'en', available: ['fr', 'en'], isRoot: false, savedChoice: 'fr' }), null);
});

test('le pluriel du lasso existe en n\u00e9erlandais', () => {
  useLang('nl');
  assert.equal(t('lasso.selected', { count: 1 }), 'adres geselecteerd');
  assert.equal(t('lasso.selected', { count: 0 }), 'adressen geselecteerd');
  assert.equal(t('lasso.selected', { count: 4 }), 'adressen geselecteerd');
});

test('le g\u00e9ocodeur UrbIS essaie la langue des donn\u00e9es puis l\u2019autre', () => {
  useLang('nl');
  assert.deepEqual(urbisLanguages(), ['nl', 'fr']);
  useLang('fr');
  assert.deepEqual(urbisLanguages(), ['fr', 'nl']);
  useLang('en');
  assert.deepEqual(urbisLanguages(), ['fr', 'nl']);
});

test('le bandeau propose le n\u00e9erlandais aux navigateurs n\u00e9erlandophones', () => {
  const base = { pageLang: 'fr', available: ['fr', 'en', 'nl'], savedChoice: null };
  assert.equal(suggestedLang({ ...base, browserLanguages: ['nl-BE', 'fr'] }), 'nl');
  assert.equal(suggestedLang({ ...base, pageLang: 'nl', browserLanguages: ['nl-BE'] }), null);
});

test('la recherche passe \u00e0 l\u2019autre langue apr\u00e8s une erreur HTTP', async () => {
  const calls = [];
  const results = await searchAcrossLanguages(['fr', 'nl'], async lang => {
    calls.push(lang);
    if (lang === 'fr') throw new Error('UrbIS HTTP 404');
    return [{ label: 'Wetstraat 16' }];
  });
  assert.deepEqual(calls, ['fr', 'nl']);
  assert.deepEqual(results, [{ label: 'Wetstraat 16' }]);
});

test('la recherche passe \u00e0 l\u2019autre langue apr\u00e8s une r\u00e9ponse vide', async () => {
  const results = await searchAcrossLanguages(['nl', 'fr'], async lang => (lang === 'nl' ? [] : [{ label: 'Rue de la Loi 16' }]));
  assert.deepEqual(results, [{ label: 'Rue de la Loi 16' }]);
});

test('aucun r\u00e9sultat si une langue r\u00e9pond vide et l\u2019autre en erreur', async () => {
  const results = await searchAcrossLanguages(['fr', 'nl'], async lang => {
    if (lang === 'fr') return [];
    throw new Error('UrbIS HTTP 404');
  });
  assert.deepEqual(results, []);
});

test('l\u2019erreur remonte si toutes les langues \u00e9chouent', async () => {
  await assert.rejects(
    searchAcrossLanguages(['fr', 'nl'], async lang => { throw new Error(`UrbIS HTTP 500 ${lang}`); }),
    /UrbIS HTTP 500 nl/
  );
});

test('le lien databrussels suit la langue de la page', () => {
  const raw = 'https://databrussels.be/id/streetname/1679/1';
  assert.equal(localizedDatabrusselsUrl(raw, 'nl'), 'https://databrussels.be/nl/id/streetname/1679/1');
  assert.equal(localizedDatabrusselsUrl(raw, 'fr'), 'https://databrussels.be/fr/id/streetname/1679/1');
  assert.equal(localizedDatabrusselsUrl(raw, 'en'), 'https://databrussels.be/en/id/streetname/1679/1');
  assert.equal(localizedDatabrusselsUrl('https://databrussels.be/fr/id/streetname/1679/1', 'nl'), 'https://databrussels.be/nl/id/streetname/1679/1');
  useLang('nl');
  assert.equal(localizedDatabrusselsUrl(raw), 'https://databrussels.be/nl/id/streetname/1679/1');
});

test('un lien qui n\u2019est pas databrussels reste inchang\u00e9', () => {
  assert.equal(localizedDatabrusselsUrl('https://example.org/id/streetname/1679/1', 'nl'), 'https://example.org/id/streetname/1679/1');
  assert.equal(localizedDatabrusselsUrl('pas une url', 'nl'), 'pas une url');
  assert.equal(localizedDatabrusselsUrl(null, 'nl'), null);
});

test('le lien de rue se construit depuis href ou depuis le code BeSt', () => {
  assert.equal(
    streetNameUrl({ href: 'https://databrussels.be/id/streetname/1679/1' }, 'en'),
    'https://databrussels.be/en/id/streetname/1679/1'
  );
  assert.equal(
    streetNameUrl({ code: { objectIdentifier: '1679', versionIdentifier: '1' } }, 'fr'),
    'https://databrussels.be/fr/id/streetname/1679/1'
  );
  assert.equal(
    streetNameUrl({ code: { objectIdentifier: '1679' } }, 'nl'),
    'https://databrussels.be/nl/id/streetname/1679'
  );
  assert.equal(streetNameUrl({}, 'fr'), null);
});
