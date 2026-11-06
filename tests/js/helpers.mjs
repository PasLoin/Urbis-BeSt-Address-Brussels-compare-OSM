import { readFileSync, readdirSync } from 'node:fs';
import { createI18n, setI18n } from '../../js/i18n.js';

export const ROOT = new URL('../../', import.meta.url);

export function readText(path) {
  return readFileSync(new URL(path, ROOT), 'utf-8');
}

export function loadDict(lang) {
  return JSON.parse(readText(`i18n/${lang}.json`));
}

export function useLang(lang) {
  const dict = { ...loadDict('fr'), ...loadDict(lang) };
  setI18n(createI18n(lang, dict));
  return dict;
}

export function availableLangs() {
  return readdirSync(new URL('i18n/', ROOT)).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)).sort();
}
