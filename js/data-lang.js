export const DATA_LANG = 'fr';

export function localStreet(props, lang = DATA_LANG) {
  const fr = props.STRNAMEFRE || '';
  const nl = props.STRNAMEDUT || '';
  if (lang === 'nl' && nl) return { primary: nl, secondary: fr };
  return { primary: fr, secondary: nl };
}

export function localMunicipality(props, lang = DATA_LANG) {
  if (lang === 'nl' && props.MUNNAMEDUT) return props.MUNNAMEDUT;
  return props.MUNNAMEFRE || '';
}

export function pickName(names, lang = DATA_LANG) {
  if (!Array.isArray(names)) return '';
  return (names.find(n => n.language === lang) || names[0] || {}).spelling || '';
}
