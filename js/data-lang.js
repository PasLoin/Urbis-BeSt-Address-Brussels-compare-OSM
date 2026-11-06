import { currentLang } from './i18n.js';

export function dataLang() {
  return currentLang() === 'nl' ? 'nl' : 'fr';
}

export function localStreet(props, lang = dataLang()) {
  const fr = props.STRNAMEFRE || '';
  const nl = props.STRNAMEDUT || '';
  if (lang === 'nl' && nl) return { primary: nl, secondary: fr };
  return { primary: fr, secondary: nl };
}

export function localMunicipality(props, lang = dataLang()) {
  if (lang === 'nl' && props.MUNNAMEDUT) return props.MUNNAMEDUT;
  return props.MUNNAMEFRE || '';
}

export function pickName(names, lang = dataLang()) {
  if (!Array.isArray(names)) return '';
  return (names.find(n => n.language === lang) || names[0] || {}).spelling || '';
}
