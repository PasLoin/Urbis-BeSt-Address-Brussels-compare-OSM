import json
import os
import re
import warnings
from pathlib import Path

import pytest

pytest.importorskip('pytest_playwright')
playwright_sync = pytest.importorskip('playwright.sync_api')
axe_sync = pytest.importorskip('axe_playwright_python.sync_playwright')
expect = playwright_sync.expect

from site_config import LANGS, REFERENCE_LANG

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = Path(os.environ.get('A11Y_REPORT_DIR', 'a11y-report'))
LANG_PATHS = {lang: conf['path'] for lang, conf in LANGS.items()}
ADDRESS_VIEW = '#17/50.8466/4.3685'
AUDIT_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
BLOCKING_TAGS = {'wcag143', 'wcag1411', 'wcag211', 'wcag212', 'wcag247', 'wcag412', 'wcag413'}
MIN_TEXT_CONTRAST = 4.5
WORST_CASE_BACKDROP = """
  .maplibregl-canvas { visibility: hidden !important; }
  #map { background: #000 !important; }
"""

AXE = axe_sync.Axe()


class A11yWarning(UserWarning):
    pass


def dictionary(lang):
    base = json.loads((ROOT / 'i18n' / f'{REFERENCE_LANG}.json').read_text(encoding='utf-8'))
    own = json.loads((ROOT / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
    return {**base, **own}


def plural(page, value, count, lang=REFERENCE_LANG):
    if isinstance(value, dict):
        form = page.evaluate('([locale, n]) => new Intl.PluralRules(locale).select(n)', [LANGS[lang]['locale'], count])
        value = value.get(form, value['other'])
    return value.replace('{count}', str(count))


def open_site(page, site_url, lang=REFERENCE_LANG, view=ADDRESS_VIEW):
    page.goto(site_url + LANG_PATHS[lang] + view, wait_until='domcontentloaded')
    expect(page.locator('#filters .filter-row')).to_have_count(5)
    expect(page.locator('#urbis-date')).not_to_have_text('…')
    page.wait_for_function('document.querySelector(".maplibregl-canvas") !== null')


def show_all_statuses(page):
    for box in page.locator('#filters input[type="checkbox"]').all():
        box.check()


def focus_map(page):
    page.locator('.maplibregl-canvas').focus()
    expect(page.locator('.maplibregl-canvas')).to_be_focused()


def open_popup_with_keyboard(page):
    show_all_statuses(page)
    focus_map(page)
    popup = page.locator('.maplibregl-popup')
    for _ in range(30):
        page.keyboard.press('Enter')
        if popup.count():
            break
        page.wait_for_timeout(500)
    expect(popup).to_be_visible()
    return popup


def focused(page):
    return page.evaluate("""() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      return el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].join('.');
    }""")


def tab_cycle(page, limit=80):
    page.evaluate('document.activeElement && document.activeElement.blur()')
    seen = []
    for _ in range(limit):
        page.keyboard.press('Tab')
        current = focused(page)
        if current is None:
            continue
        if seen and current == seen[0]:
            return seen, True
        seen.append(current)
    return seen, False


def has_focus_indicator(page):
    return page.evaluate("""() => {
      const visible = el => {
        const s = getComputedStyle(el);
        const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2;
        return outline || s.boxShadow !== 'none';
      };
      const el = document.activeElement;
      if (visible(el)) return true;
      const host = el.closest('#search-bar');
      return Boolean(host && visible(host));
    }""")


def contrast_ratio(page, fg, bg):
    return page.evaluate("""([fg, bg]) => {
      const parse = c => c.match(/[\\d.]+/g).slice(0, 3).map(Number);
      const lum = rgb => {
        const [r, g, b] = rgb.map(v => {
          v /= 255;
          return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const [a, b] = [lum(parse(fg)), lum(parse(bg))].sort((x, y) => y - x);
      return (a + 0.05) / (b + 0.05);
    }""", [fg, bg])


def run_axe(page, state):
    page.add_style_tag(content=WORST_CASE_BACKDROP)
    page.wait_for_timeout(100)
    result = AXE.run(page, options={
        'runOnly': {'type': 'tag', 'values': AUDIT_TAGS},
        'resultTypes': ['violations', 'incomplete'],
    }).response
    blocking, other = [], []
    for violation in result['violations']:
        (blocking if BLOCKING_TAGS & set(violation['tags']) else other).append(violation)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f'{state}.json').write_text(json.dumps({
        'state': state,
        'blocking': blocking,
        'warnings': other,
        'incomplete': result.get('incomplete', []),
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    for violation in other:
        targets = ', '.join(str(node['target']) for node in violation['nodes'][:3])
        warnings.warn(f"[{state}] {violation['id']} ({violation['impact']}) : {violation['help']} → {targets}", A11yWarning)
    for item in result.get('incomplete', []):
        if BLOCKING_TAGS & set(item['tags']):
            targets = ', '.join(str(node['target']) for node in item['nodes'][:3])
            warnings.warn(f"[{state}] {item['id']} à vérifier à la main : {item['help']} → {targets}", A11yWarning)
    return blocking


def describe(violations):
    lines = []
    for violation in violations:
        lines.append(f"{violation['id']} : {violation['help']}")
        for node in violation['nodes'][:5]:
            lines.append(f"    {node['target']} {node.get('failureSummary', '').splitlines()[-1:]}")
    return '\n'.join(lines)


def state_initial(page):
    pass


def state_search_results(page):
    page.click('#search-toggle')
    page.fill('#search-input', 'Rue de la Loi 16')
    expect(page.locator('#search-dropdown li[role="option"]').first).to_be_visible(timeout=15000)
    page.keyboard.press('ArrowDown')


def state_search_status(page):
    page.click('#search-toggle')
    page.click('.src-btn[data-src="urbis"]')
    page.fill('#search-input', 'Rue de la Loi')
    expect(page.locator('#search-dropdown li.status-row')).to_be_visible()


def state_basemap_menu(page):
    page.click('#basemap-toggle')
    expect(page.locator('#basemap-menu')).to_be_visible()


def state_lang_menu(page):
    page.click('#lang-toggle')
    expect(page.locator('#lang-menu')).to_be_visible()


def state_popup(page):
    open_popup_with_keyboard(page)


def state_lasso_panel(page):
    show_all_statuses(page)
    page.click('#lasso-btn')
    focus_map(page)
    page.keyboard.press('Enter')
    expect(page.locator('#lasso-panel')).to_be_visible()


def state_toast(page):
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
    popup = open_popup_with_keyboard(page)
    copy = popup.locator('.copy-id-btn')
    if not copy.count():
        pytest.skip('adresse sans identifiant INSPIRE au centre de la carte')
    copy.click()
    expect(page.locator('#copy-toast')).to_be_visible()


STATES = {
    'initial': state_initial,
    'recherche-resultats': state_search_results,
    'recherche-statut': state_search_status,
    'menu-fond-de-carte': state_basemap_menu,
    'menu-langue': state_lang_menu,
    'popup-adresse': state_popup,
    'panneau-lasso': state_lasso_panel,
    'toast': state_toast,
}


AXE_CASES = [(lang, 'initial') for lang in LANG_PATHS] + [(REFERENCE_LANG, state) for state in STATES if state != 'initial']


@pytest.mark.parametrize('lang,state', AXE_CASES, ids=[f'{lang}-{state}' for lang, state in AXE_CASES])
def test_axe_sans_violation_bloquante(page, site_url, lang, state):
    open_site(page, site_url, lang)
    STATES[state](page)
    blocking = run_axe(page, f'{lang}-{state}')
    assert not blocking, describe(blocking)


def test_placeholder_contraste_suffisant(page, site_url):
    open_site(page, site_url)
    page.click('#search-toggle')
    colors = page.evaluate("""() => ({
      fg: getComputedStyle(document.getElementById('search-input'), '::placeholder').color,
      bg: getComputedStyle(document.getElementById('search-bar')).backgroundColor,
    })""")
    assert contrast_ratio(page, colors['fg'], colors['bg']) >= MIN_TEXT_CONTRAST, colors


def test_parcours_clavier_sans_piege(page, site_url):
    open_site(page, site_url)
    sequence, cycled = tab_cycle(page)
    assert cycled, f'la tabulation ne revient pas au début : {sequence}'
    for control in ('canvas.maplibregl-canvas', '#lasso-btn', '#search-toggle', '#basemap-toggle', '#lang-toggle'):
        assert control in sequence, f'{control} absent du parcours clavier : {sequence}'
    assert '#search-input' not in sequence, 'le champ de recherche replié reste atteignable sans être visible'


@pytest.mark.parametrize('setup', ['replie', 'recherche-ouverte'])
def test_focus_toujours_visible(page, site_url, setup):
    open_site(page, site_url)
    if setup == 'recherche-ouverte':
        page.click('#search-toggle')
        page.fill('#search-input', 'Rue')
    page.evaluate('document.activeElement && document.activeElement.blur()')
    missing = []
    for _ in range(40):
        page.keyboard.press('Tab')
        current = focused(page)
        if current and not has_focus_indicator(page):
            missing.append(current)
    assert not missing, f'focus invisible sur : {sorted(set(missing))}'


def test_adresse_ouverte_au_clavier(page, site_url):
    open_site(page, site_url)
    expect(page.locator('.maplibregl-canvas')).to_have_attribute('aria-describedby', 'map-help')
    popup = open_popup_with_keyboard(page)
    assert page.evaluate("document.querySelector('.maplibregl-popup').contains(document.activeElement)")
    for _ in range(12):
        if page.evaluate("document.activeElement.textContent.trim() === 'JOSM'"):
            break
        page.keyboard.press('Tab')
    else:
        pytest.fail('lien JOSM non atteignable au clavier dans le popup')
    page.keyboard.press('Escape')
    expect(popup).to_have_count(0)
    expect(page.locator('.maplibregl-canvas')).to_be_focused()


@pytest.mark.parametrize('menu', ['basemap', 'lang'])
def test_menu_echap_rend_le_focus(page, site_url, menu):
    open_site(page, site_url)
    toggle = page.locator(f'#{menu}-toggle')
    toggle.focus()
    page.keyboard.press('Enter')
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    page.keyboard.press('Tab')
    assert page.evaluate(f"document.getElementById('{menu}-menu').contains(document.activeElement)")
    page.keyboard.press('Escape')
    expect(page.locator(f'#{menu}-menu')).to_be_hidden()
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    expect(toggle).to_be_focused()


def test_recherche_combobox_et_echap(page, site_url):
    strings = dictionary(REFERENCE_LANG)
    open_site(page, site_url)
    toggle = page.locator('#search-toggle')
    toggle.focus()
    page.keyboard.press('Enter')
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    field = page.locator('#search-input')
    expect(field).to_be_focused()
    expect(field).to_have_attribute('role', 'combobox')
    page.keyboard.type('Rue de la Loi 16')
    options = page.locator('#search-dropdown[role="listbox"] li[role="option"]')
    expect(options.first).to_be_visible(timeout=15000)
    expect(field).to_have_attribute('aria-expanded', 'true')
    count = options.count()
    expect(page.locator('#a11y-status')).to_have_text(plural(page, strings['search.resultCount'], count))
    page.keyboard.press('ArrowDown')
    active_id = field.get_attribute('aria-activedescendant')
    assert active_id
    expect(page.locator(f'#{active_id}')).to_have_attribute('aria-selected', 'true')
    page.keyboard.press('Escape')
    expect(field).to_have_attribute('aria-expanded', 'false')
    expect(field).to_be_focused()
    page.keyboard.press('Escape')
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    expect(toggle).to_be_focused()


def test_lasso_au_clavier_annonce_la_selection(page, site_url):
    strings = dictionary(REFERENCE_LANG)
    open_site(page, site_url)
    show_all_statuses(page)
    button = page.locator('#lasso-btn')
    button.focus()
    page.keyboard.press('Enter')
    expect(button).to_have_attribute('aria-pressed', 'true')
    status = page.locator('#a11y-status')
    expect(status).to_have_text(strings['lasso.activeHelp'])
    focus_map(page)
    page.keyboard.press('Enter')
    expect(page.locator('#lasso-panel')).to_be_visible()
    expect(page.locator('#lasso-export')).to_be_focused()
    expect(button).to_have_attribute('aria-pressed', 'false')
    count = int(page.locator('#lasso-count').inner_text())
    expect(status).to_have_text(f"{count} {plural(page, strings['lasso.selected'], count)}")
    page.keyboard.press('Escape')
    expect(page.locator('#lasso-panel')).to_be_hidden()
    expect(button).to_be_focused()


def test_regions_de_statut_presentes(page, site_url):
    open_site(page, site_url)
    status = page.locator('#a11y-status')
    expect(status).to_have_attribute('role', 'status')
    expect(status).to_have_attribute('aria-live', 'polite')
    expect(page.locator('#copy-toast')).to_have_attribute('aria-hidden', 'true')
    expect(page.locator('#stats-bar')).to_have_attribute('aria-hidden', 'true')
