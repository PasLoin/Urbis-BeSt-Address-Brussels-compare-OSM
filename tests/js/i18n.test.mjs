import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createI18n, setI18n, getI18n, i18nFromDocument } from '../../js/i18n.js';
import { suggestedLang, redirectTarget, primaryBrowserLang } from '../../js/lang.js';
import { generateOsmXml } from '../../js/osm-export.js';
import { dataLang, localStreet } from '../../js/data-lang.js';
import { buildUrbisUrl, urbisLanguages, searchAcrossLanguages, streetNameUrl } from '../../js/search.js';
import { localizedDatabrusselsUrl } from '../../js/databrussels.js';
import { i18nFor, LANGUAGES, availableLangs } from './helpers.mjs';

const BASE = { lang: 'fr', locale: 'fr-BE', dataLang: 'fr', timeZone: 'Europe/Brussels' };
const DICT = {
  greeting: 'Bonjour {name}',
  items: { one: '{count} \u00e9l\u00e9ment', other: '{count} \u00e9l\u00e9ments' }
};

test('t remplace les variables et garde celles qui manquent', () => {
  const i18n = createI18n({ ...BASE, dict: DICT });
  assert.equal(i18n.t('greeting', { name: 'Bruxelles' }), 'Bonjour Bruxelles');
  assert.equal(i18n.t('greeting'), 'Bonjour {name}');
});

test('une cl\u00e9 inconnue est rendue telle quelle et signal\u00e9e une seule fois', () => {
  const reported = [];
  const i18n = createI18n({ ...BASE, dict: DICT, onMissing: (key, lang) => reported.push(`${lang}:${key}`) });
  assert.equal(i18n.t('absente'), 'absente');
  assert.equal(i18n.t('absente'), 'absente');
  assert.equal(i18n.t('greeting', { name: 'x' }), 'Bonjour x');
  assert.deepEqual(reported, ['fr:absente']);
  assert.equal(createI18n({ ...BASE, dict: DICT }).t('absente'), 'absente');
});

test('les pluriels suivent les r\u00e8gles de chaque langue', () => {
  const fr = createI18n({ ...BASE, dict: DICT });
  assert.equal(fr.t('items', { count: 0 }), '0 \u00e9l\u00e9ment');
  assert.equal(fr.t('items', { count: 1 }), '1 \u00e9l\u00e9ment');
  assert.equal(fr.t('items', { count: 2 }), '2 \u00e9l\u00e9ments');
  const en = createI18n({ lang: 'en', locale: 'en-GB', dataLang: 'fr', timeZone: 'Europe/Brussels', dict: { items: { one: '{count} item', other: '{count} items' } } });
  assert.equal(en.t('items', { count: 0 }), '0 items');
  assert.equal(en.t('items', { count: 1 }), '1 item');
});

test('une instance est fig\u00e9e', () => {
  const i18n = createI18n({ ...BASE, dict: DICT });
  assert.ok(Object.isFrozen(i18n));
});

test('l\u2019instance de l\u2019application refuse d\u2019\u00eatre lue avant initialisation', () => {
  setI18n(null);
  assert.throws(() => getI18n(), /setI18n/);
  assert.throws(() => dataLang(), /setI18n/);
  const nl = i18nFor('nl');
  setI18n(nl);
  assert.equal(getI18n(), nl);
  assert.equal(dataLang(), 'nl');
  assert.equal(buildUrbisUrl('Wetstraat 16').searchParams.get('searchLanguage'), 'nl');
  setI18n(null);
});

test('chaque langue d\u00e9clar\u00e9e fournit locale, langue des donn\u00e9es et fuseau', () => {
  for (const lang of availableLangs()) {
    const i18n = i18nFor(lang);
    assert.equal(i18n.lang, lang);
    assert.equal(i18n.locale, LANGUAGES.languages[lang].locale);
    assert.ok(['fr', 'nl'].includes(i18n.dataLang));
    assert.equal(i18n.timeZone, LANGUAGES.timeZone);
  }
});

test('i18nFromDocument lit la configuration pos\u00e9e sur la page', () => {
  const doc = {
    documentElement: { lang: 'nl', dataset: { locale: 'nl-BE', dataLang: 'nl', timeZone: 'Europe/Brussels' } },
    getElementById: id => (id === 'i18n-dict' ? { textContent: '{"hello":"Hallo"}' } : null)
  };
  const i18n = i18nFromDocument(doc, { warnMissing: false });
  assert.equal(i18n.lang, 'nl');
  assert.equal(i18n.locale, 'nl-BE');
  assert.equal(i18n.dataLang, 'nl');
  assert.equal(i18n.t('hello'), 'Hallo');
});

test('les langues des donn\u00e9es viennent de la configuration, pas d\u2019un \u00e9tat global', () => {
  assert.equal(i18nFor('en').dataLang, 'fr');
  assert.equal(i18nFor('nl').dataLang, 'nl');
  assert.deepEqual(localStreet({ STRNAMEFRE: 'Rue de la Loi', STRNAMEDUT: 'Wetstraat' }, i18nFor('nl').dataLang), { primary: 'Wetstraat', secondary: 'Rue de la Loi' });
  assert.equal(buildUrbisUrl('Wetstraat 16', i18nFor('nl').dataLang).searchParams.get('searchLanguage'), 'nl');
});

test('le pluriel du lasso existe dans chaque langue', () => {
  const fr = i18nFor('fr');
  assert.equal(fr.t('lasso.selected', { count: 1 }), 'adresse s\u00e9lectionn\u00e9e');
  assert.equal(fr.t('lasso.selected', { count: 3 }), 'adresses s\u00e9lectionn\u00e9es');
  const en = i18nFor('en');
  assert.equal(en.t('lasso.selected', { count: 1 }), 'address selected');
  assert.equal(en.t('lasso.selected', { count: 0 }), 'addresses selected');
  const nl = i18nFor('nl');
  assert.equal(nl.t('lasso.selected', { count: 1 }), 'adres geselecteerd');
  assert.equal(nl.t('lasso.selected', { count: 0 }), 'adressen geselecteerd');
  assert.equal(nl.t('lasso.selected', { count: 4 }), 'adressen geselecteerd');
});

test('l\u2019export .osm ne d\u00e9pend d\u2019aucune langue', () => {
  const features = [{
    properties: { STRNAMEFRE: 'Rue de la Loi', STRNAMEDUT: 'Wetstraat', POLICENUM: '16', INSPIRE_ID: 'X/1' },
    lng: 4.3685,
    lat: 50.8466
  }];
  setI18n(null);
  assert.equal(generateOsmXml(features), generateOsmXml(features));
  assert.match(generateOsmXml(features), /Rue de la Loi - Wetstraat/);
});

test('le g\u00e9ocodeur UrbIS essaie la langue des donn\u00e9es puis l\u2019autre', () => {
  assert.deepEqual(urbisLanguages(i18nFor('nl').dataLang), ['nl', 'fr']);
  assert.deepEqual(urbisLanguages(i18nFor('fr').dataLang), ['fr', 'nl']);
  assert.deepEqual(urbisLanguages(i18nFor('en').dataLang), ['fr', 'nl']);
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
  assert.equal(localizedDatabrusselsUrl(raw, i18nFor('nl').lang), 'https://databrussels.be/nl/id/streetname/1679/1');
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
