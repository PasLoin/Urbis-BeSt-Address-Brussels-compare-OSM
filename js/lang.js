import { currentLang } from './i18n.js';

export const LANG_STORAGE_KEY = 'urbis-osm-lang';

function readChoice() {
  try { return localStorage.getItem(LANG_STORAGE_KEY); } catch (e) { return null; }
}

function saveChoice(lang) {
  try { localStorage.setItem(LANG_STORAGE_KEY, lang); } catch (e) {}
}

export function primaryBrowserLang(languages) {
  const first = (languages || [])[0];
  return first ? first.slice(0, 2).toLowerCase() : null;
}

export function suggestedLang({ pageLang, available, browserLanguages, savedChoice }) {
  if (savedChoice) return null;
  const primary = primaryBrowserLang(browserLanguages);
  if (!primary || primary === pageLang || !available.includes(primary)) return null;
  return primary;
}

export function redirectTarget({ pageLang, isRoot, savedChoice, available }) {
  if (!isRoot || !savedChoice || savedChoice === pageLang || !available.includes(savedChoice)) return null;
  return savedChoice;
}

function languageLinks() {
  return Object.fromEntries(
    [...document.querySelectorAll('#lang-menu [data-lang]')].map(a => [a.dataset.lang, a.href])
  );
}

function goTo(href) {
  location.assign(href + location.hash);
}

export function redirectToSavedLanguage() {
  const links = languageLinks();
  const target = redirectTarget({
    pageLang: currentLang(),
    isRoot: document.documentElement.dataset.root === 'true',
    savedChoice: readChoice(),
    available: Object.keys(links)
  });
  if (!target) return false;
  location.replace(links[target] + location.hash);
  return true;
}

export function initLanguageControl() {
  const control = document.getElementById('lang-control');
  const toggle = document.getElementById('lang-toggle');

  function setMenuOpen(open) {
    control.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  toggle.addEventListener('click', e => {
    e.stopPropagation();
    setMenuOpen(!control.classList.contains('open'));
  });
  document.addEventListener('click', e => {
    if (!control.contains(e.target)) setMenuOpen(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') setMenuOpen(false);
  });
  document.querySelectorAll('#lang-menu [data-lang]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      saveChoice(link.dataset.lang);
      setMenuOpen(false);
      if (link.dataset.lang !== currentLang()) goTo(link.href);
    });
  });
}

export function initLanguageBanner() {
  const links = languageLinks();
  const target = suggestedLang({
    pageLang: currentLang(),
    available: Object.keys(links),
    browserLanguages: navigator.languages,
    savedChoice: readChoice()
  });
  if (!target) return;
  const banners = JSON.parse(document.getElementById('i18n-banners').textContent);
  const strings = banners[target];
  if (!strings) return;
  const banner = document.getElementById('lang-banner');
  const switchLink = document.getElementById('lang-banner-switch');
  const close = document.getElementById('lang-banner-close');
  banner.lang = target;
  document.getElementById('lang-banner-text').textContent = strings.text;
  switchLink.textContent = strings.switch;
  switchLink.href = links[target];
  switchLink.hreflang = target;
  close.title = strings.dismiss;
  close.setAttribute('aria-label', strings.dismiss);
  switchLink.addEventListener('click', e => {
    e.preventDefault();
    saveChoice(target);
    goTo(links[target]);
  });
  close.addEventListener('click', () => {
    saveChoice(currentLang());
    banner.hidden = true;
  });
  banner.hidden = false;
}
