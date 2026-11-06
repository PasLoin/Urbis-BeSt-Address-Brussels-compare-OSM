import os
import re
from pathlib import Path

import pytest

pytest.importorskip('pytest_playwright')
playwright_sync = pytest.importorskip('playwright.sync_api')
expect = playwright_sync.expect

SCREENSHOT_DIR = Path(os.environ.get('SCREENSHOT_DIR', 'screenshots'))
VIEWPORTS = {'bureau': {'width': 1280, 'height': 800}, 'mobile': {'width': 390, 'height': 844}}


@pytest.fixture
def errors(page):
    collected = []
    page.on('pageerror', lambda exc: collected.append(str(exc)))
    return collected


def open_site(page, site_url):
    page.goto(site_url, wait_until='domcontentloaded')
    expect(page.locator('#filters .filter-row')).to_have_count(5)


def test_chargement_sans_erreur(page, site_url, errors):
    open_site(page, site_url)
    expect(page.locator('#urbis-date')).not_to_have_text('…')
    expect(page.locator('#stats-rows .stats-row').first).to_contain_text('Total UrbIS')
    page.wait_for_function('document.querySelector(".maplibregl-canvas") !== null')
    assert errors == []


def test_filtres_initiaux(page, site_url):
    open_site(page, site_url)
    expect(page.locator('#f-missing')).to_be_checked()
    expect(page.locator('#f-ok')).not_to_be_checked()


def test_recherche_osm(page, site_url, errors):
    open_site(page, site_url)
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


@pytest.mark.parametrize('name', list(VIEWPORTS))
def test_captures(page, site_url, name):
    page.set_viewport_size(VIEWPORTS[name])
    open_site(page, site_url)
    page.wait_for_timeout(2000)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / f'fr-{name}.png'))
