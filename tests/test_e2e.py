import json
import os
import re
from pathlib import Path

import pytest

pytest.importorskip('pytest_playwright')
playwright_sync = pytest.importorskip('playwright.sync_api')
expect = playwright_sync.expect

ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = Path(os.environ.get('SCREENSHOT_DIR', 'screenshots'))
VIEWPORTS = {'bureau': {'width': 1280, 'height': 800}, 'mobile': {'width': 390, 'height': 844}}
LANG_PATHS = {'fr': '', 'en': 'en/'}


def dictionary(lang):
    base = json.loads((ROOT / 'i18n' / 'fr.json').read_text(encoding='utf-8'))
    own = json.loads((ROOT / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
    return {**base, **own}


def french_only_strings():
    fr, en = dictionary('fr'), dictionary('en')
    found = set()
    for key, value in fr.items():
        values = value.values() if isinstance(value, dict) else [value]
        other = en[key].values() if isinstance(en[key], dict) else [en[key]]
        for text in values:
            text = re.sub(r'\{\w+\}', '', text).strip()
            if len(text) >= 5 and text not in other:
                found.add(text)
    return found


@pytest.fixture
def errors(page):
    collected = []
    page.on('pageerror', lambda exc: collected.append(str(exc)))
    return collected


def open_site(page, site_url, lang='fr'):
    page.goto(site_url + LANG_PATHS[lang], wait_until='domcontentloaded')
    expect(page.locator('#filters .filter-row')).to_have_count(5)


@pytest.mark.parametrize('lang', LANG_PATHS)
def test_chargement_sans_erreur(page, site_url, errors, lang):
    strings = dictionary(lang)
    open_site(page, site_url, lang)
    expect(page.locator('html')).to_have_attribute('lang', lang)
    expect(page.locator('#urbis-date')).not_to_have_text('…')
    expect(page.locator('#stats-rows .stats-row').first).to_contain_text(strings['stats.total'])
    expect(page.locator('#filters')).to_contain_text(strings['status.missing'])
    page.wait_for_function('document.querySelector(".maplibregl-canvas") !== null')
    assert errors == []


def test_aucun_texte_francais_en_anglais(page, site_url):
    open_site(page, site_url, 'en')
    expect(page.locator('#stats-rows .stats-row').first).to_contain_text('UrbIS total')
    visible = page.locator('body').inner_text()
    attributes = page.evaluate(
        "[...document.querySelectorAll('[title],[aria-label],[placeholder]')]"
        ".flatMap(e => [e.title, e.getAttribute('aria-label'), e.placeholder]).filter(Boolean).join('\\n')"
    )
    leaks = sorted(text for text in french_only_strings() if text in visible or text in attributes)
    assert leaks == []


def test_filtres_initiaux(page, site_url):
    open_site(page, site_url)
    expect(page.locator('#f-missing')).to_be_checked()
    expect(page.locator('#f-ok')).not_to_be_checked()


@pytest.mark.parametrize('lang', LANG_PATHS)
def test_recherche_osm(page, site_url, errors, lang):
    open_site(page, site_url, lang)
    page.click('#search-toggle')
    page.fill('#search-input', 'Rue de la Loi 16')
    first = page.locator('#search-dropdown li[role="option"]').first
    expect(first).to_contain_text(re.compile('Rue de la Loi', re.I), timeout=15000)
    page.keyboard.press('Escape')
    expect(page.locator('#search-dropdown')).not_to_have_class(re.compile(r'\bopen\b'))
    assert errors == []


def test_lasso_et_echap(page, site_url):
    open_site(page, site_url)
    page.click('#lasso-btn')
    expect(page.locator('#lasso-btn')).to_have_class(re.compile(r'\bactive\b'))
    page.keyboard.press('Escape')
    expect(page.locator('#lasso-btn')).not_to_have_class(re.compile(r'\bactive\b'))


def test_changement_de_langue_garde_la_position(page, site_url):
    open_site(page, site_url)
    page.goto(site_url + '#15/50.8466/4.3685', wait_until='domcontentloaded')
    expect(page.locator('#filters .filter-row')).to_have_count(5)
    page.click('#lang-toggle')
    page.click('#lang-menu [data-lang="en"]')
    page.wait_for_url(re.compile(r'/en/#15/50\.8466/4\.3685'))
    expect(page.locator('html')).to_have_attribute('lang', 'en')
    assert page.evaluate("localStorage.getItem('urbis-osm-lang')") == 'en'


def test_choix_memorise_redirige_depuis_la_racine(page, site_url):
    open_site(page, site_url)
    page.evaluate("localStorage.setItem('urbis-osm-lang', 'en')")
    page.goto(site_url, wait_until='domcontentloaded')
    page.wait_for_url(re.compile(r'/en/'))
    expect(page.locator('html')).to_have_attribute('lang', 'en')


def test_lien_partage_vers_une_langue_respecte(page, site_url):
    open_site(page, site_url, 'en')
    page.evaluate("localStorage.setItem('urbis-osm-lang', 'fr')")
    page.goto(site_url + 'en/', wait_until='domcontentloaded')
    expect(page.locator('#filters .filter-row')).to_have_count(5)
    expect(page.locator('html')).to_have_attribute('lang', 'en')


@pytest.mark.parametrize('visible', [
    pytest.param(True, id='en-US', marks=pytest.mark.browser_context_args(locale='en-US')),
    pytest.param(False, id='fr-BE', marks=pytest.mark.browser_context_args(locale='fr-BE')),
    pytest.param(False, id='nl-BE', marks=pytest.mark.browser_context_args(locale='nl-BE')),
])
def test_bandeau_selon_la_langue_du_navigateur(page, site_url, visible):
    open_site(page, site_url)
    banner = page.locator('#lang-banner')
    if visible:
        expect(banner).to_be_visible()
        expect(banner).to_contain_text('This map is also available in English.')
        page.click('#lang-banner-close')
        expect(banner).to_be_hidden()
        assert page.evaluate("localStorage.getItem('urbis-osm-lang')") == 'fr'
    else:
        page.wait_for_timeout(500)
        expect(banner).to_be_hidden()


@pytest.mark.parametrize('lang', LANG_PATHS)
@pytest.mark.parametrize('name', list(VIEWPORTS))
def test_captures(page, site_url, name, lang):
    page.set_viewport_size(VIEWPORTS[name])
    open_site(page, site_url, lang)
    page.wait_for_timeout(2000)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / f'{lang}-{name}.png'))
