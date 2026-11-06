import { readFileSync } from 'node:fs';
import { createI18n } from '../../js/i18n.js';

export const ROOT = new URL('../../', import.meta.url);

export function readText(path) {
  return readFileSync(new URL(path, ROOT), 'utf-8');
}

export const LANGUAGES = JSON.parse(readText('i18n/languages.json'));

export function loadDict(lang) {
  return JSON.parse(readText(`i18n/${lang}.json`));
}

export function availableLangs() {
  return Object.keys(LANGUAGES.languages);
}

export function failOnMissing(lang) {
  return key => {
    throw new Error(`cl\u00e9 absente (${lang}) : ${key}`);
  };
}

export function i18nFor(lang) {
  const conf = LANGUAGES.languages[lang];
  return createI18n({
    lang,
    locale: conf.locale,
    dataLang: conf.data,
    timeZone: LANGUAGES.timeZone,
    dict: { ...loadDict(LANGUAGES.reference), ...loadDict(lang) },
    onMissing: failOnMissing(lang)
  });
}
