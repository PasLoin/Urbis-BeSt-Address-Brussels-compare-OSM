import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

from site_config import LANGS, REFERENCE_LANG, SITE_URL

ROOT = Path(__file__).resolve().parent.parent
PAGES = {
    f"{conf['path']}index.html": {'lang': lang, 'url': SITE_URL + conf['path'], 'og': conf['og']}
    for lang, conf in LANGS.items()
}
EXPECTED_ALTERNATES = {(conf['lang'], conf['url']) for conf in PAGES.values()} | {('x-default', SITE_URL)}
PUBLIC_FILES = [
    'taginfo.json',
    'assets/img/cecinestpasunerue.png',
    'assets/img/favicon.ico',
    'assets/img/apple-touch-icon.png',
    'addresses.pmtiles',
    'search-index.json',
    'version.json',
]


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.alternates = set()
        self.meta = {}
        self.meta_all = []
        self.canonical = None
        self.lang = None
        self.title = ''
        self.scripts = {}
        self._in = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang')
        if tag in ('script', 'img') and a.get('src'):
            self.links.append(a['src'])
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag == 'link' and a.get('href'):
            rel = a.get('rel')
            if rel == 'canonical':
                self.canonical = a['href']
            elif rel == 'alternate':
                self.alternates.add((a.get('hreflang'), a['href']))
            else:
                self.links.append(a['href'])
        if tag == 'meta' and a.get('property'):
            self.meta.setdefault(a['property'], a.get('content'))
            self.meta_all.append((a['property'], a.get('content')))
        if tag == 'title':
            self._in = 'title'
        if tag == 'script' and a.get('id'):
            self._in = a['id']
            self.scripts[a['id']] = ''

    def handle_endtag(self, tag):
        if tag in ('title', 'script'):
            self._in = None

    def handle_data(self, data):
        if self._in == 'title':
            self.title += data
        elif self._in:
            self.scripts[self._in] += data


def parse(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding='utf-8'))
    return parser


def is_local(url):
    parsed = urlparse(url)
    return not parsed.scheme and not parsed.netloc and not url.startswith(('#', 'data:'))


def dictionary(lang):
    base = json.loads((ROOT / 'i18n' / f'{REFERENCE_LANG}.json').read_text(encoding='utf-8'))
    own = json.loads((ROOT / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))
    return {**base, **own}


@pytest.mark.parametrize('page', PAGES)
def test_page_sans_balise_jinja(site_dir, page):
    assert not re.search(r'\{\{|\{%|\{#', (site_dir / page).read_text(encoding='utf-8'))


@pytest.mark.parametrize('page', PAGES)
def test_langue_url_et_locale(site_dir, page):
    conf = PAGES[page]
    doc = parse(site_dir / page)
    assert doc.lang == conf['lang']
    assert doc.canonical == conf['url']
    assert doc.meta.get('og:url') == conf['url']
    assert doc.meta.get('og:locale') == conf['og']
    alternates = {content for prop, content in doc.meta_all if prop == 'og:locale:alternate'}
    assert alternates == {c['og'] for c in PAGES.values()} - {conf['og']}


@pytest.mark.parametrize('page', PAGES)
def test_hreflang_reciproques(site_dir, page):
    assert parse(site_dir / page).alternates == EXPECTED_ALTERNATES


@pytest.mark.parametrize('page', PAGES)
def test_titre_et_dictionnaire_de_la_langue(site_dir, page):
    conf = PAGES[page]
    doc = parse(site_dir / page)
    expected = dictionary(conf['lang'])
    assert doc.title == expected['meta.title']
    assert json.loads(doc.scripts['i18n-dict']) == expected
    banners = json.loads(doc.scripts['i18n-banners'])
    assert set(banners) == {c['lang'] for c in PAGES.values()}


def test_titres_differents_par_langue(site_dir):
    titles = {parse(site_dir / page).title for page in PAGES}
    assert len(titles) == len(PAGES)


@pytest.mark.parametrize('page', PAGES)
def test_liens_locaux_existent(site_dir, page):
    doc = parse(site_dir / page)
    base = (site_dir / page).parent
    local = [link for link in doc.links if is_local(link)]
    assert local
    for link in local:
        target = (base / link).resolve()
        if link.endswith('/'):
            target = target / 'index.html'
        assert target.is_file(), link


def test_imports_js_existent(site_dir):
    for module in (site_dir / 'js').glob('*.js'):
        for target in re.findall(r"from '(\./[^']+)'", module.read_text(encoding='utf-8')):
            assert (module.parent / target).is_file(), f'{module.name} importe {target}'


@pytest.mark.parametrize('page', PAGES)
def test_image_de_partage_publiee(site_dir, page):
    image = parse(site_dir / page).meta.get('og:image', '')
    assert image.startswith(SITE_URL)
    assert (site_dir / image[len(SITE_URL):]).is_file()


@pytest.mark.parametrize('name', PUBLIC_FILES)
def test_fichiers_publics_presents(site_dir, name):
    assert (site_dir / name).is_file()


def test_taginfo_valide(site_dir):
    project = json.loads((site_dir / 'taginfo.json').read_text(encoding='utf-8'))['project']
    assert project['project_url'].rstrip('/') == SITE_URL.rstrip('/')


def test_pas_de_fichiers_de_travail_publies(site_dir):
    published = {p.name for p in site_dir.iterdir()}
    for name in ('tests', 'templates', 'i18n', 'node_modules', '.github', 'fetch-latest.py', 'build-site.py', 'README.md'):
        assert name not in published
