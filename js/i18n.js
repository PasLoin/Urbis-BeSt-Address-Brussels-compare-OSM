const DEV_HOSTS = ['localhost', '127.0.0.1'];

export function createI18n({ lang, locale, dataLang, timeZone, dict = {}, onMissing = null }) {
  const plural = new Intl.PluralRules(locale);
  const reported = new Set();
  const t = (key, vars = {}) => {
    let s = dict[key];
    if (s === undefined) {
      if (onMissing && !reported.has(key)) {
        reported.add(key);
        onMissing(key, lang);
      }
      s = key;
    }
    if (s && typeof s === 'object') s = s[plural.select(vars.count ?? 0)] ?? s.other;
    return String(s).replace(/\{(\w+)\}/g, (match, k) => (k in vars ? String(vars[k]) : match));
  };
  return Object.freeze({ lang, locale, dataLang, timeZone, t });
}

let appI18n = null;

export function setI18n(instance) {
  appI18n = instance;
}

export function getI18n() {
  if (!appI18n) throw new Error('i18n not initialised: call setI18n() first');
  return appI18n;
}

export function isDevHost(hostname = globalThis.location?.hostname) {
  return DEV_HOSTS.includes(hostname);
}

export function warnMissingKey(key, lang) {
  console.warn(`[i18n] clé absente (${lang}) : ${key}`);
}

export function i18nFromDocument(doc = document, { warnMissing = isDevHost() } = {}) {
  const root = doc.documentElement;
  return createI18n({
    lang: root.lang,
    locale: root.dataset.locale,
    dataLang: root.dataset.dataLang,
    timeZone: root.dataset.timeZone,
    dict: JSON.parse(doc.getElementById('i18n-dict').textContent),
    onMissing: warnMissing ? warnMissingKey : null
  });
}
