export const LOCALES = { fr: 'fr-BE', en: 'en-GB', nl: 'nl-BE' };
export const TIME_ZONE = 'Europe/Brussels';

export function createI18n(lang, dict) {
  const locale = LOCALES[lang] ?? LOCALES.fr;
  const plural = new Intl.PluralRules(locale);
  const t = (key, vars = {}) => {
    let s = dict[key] ?? key;
    if (s && typeof s === 'object') s = s[plural.select(vars.count ?? 0)] ?? s.other;
    return String(s).replace(/\{(\w+)\}/g, (match, k) => (k in vars ? String(vars[k]) : match));
  };
  return { lang, locale, t };
}

let current = createI18n('fr', {});

export function setI18n(instance) {
  current = instance;
}

export function t(key, vars) {
  return current.t(key, vars);
}

export function currentLang() {
  return current.lang;
}

export function currentLocale() {
  return current.locale;
}

export function i18nFromDocument(doc = document) {
  const dict = JSON.parse(doc.getElementById('i18n-dict').textContent);
  return createI18n(doc.documentElement.lang, dict);
}
