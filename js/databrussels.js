import { getI18n } from './i18n.js';

export const DATABRUSSELS_HOST = 'databrussels.be';
const DATABRUSSELS_LANGS = ['fr', 'nl', 'en'];

export function localizedDatabrusselsUrl(url, lang = getI18n().lang) {
  if (!url) return null;
  let parsed;
  try {
    parsed = new URL(url);
  } catch (e) {
    return url;
  }
  if (parsed.hostname !== DATABRUSSELS_HOST || !DATABRUSSELS_LANGS.includes(lang)) return url;
  const path = parsed.pathname.replace(/^\/(fr|nl|en)(?=\/)/, '');
  parsed.pathname = `/${lang}${path}`;
  return parsed.href;
}
