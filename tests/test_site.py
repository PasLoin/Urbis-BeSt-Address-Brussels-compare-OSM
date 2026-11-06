import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import pytest

SITE_URL = 'https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/'
PAGES = ['index.html']
PUBLIC_FILES = [
    'taginfo.json',
    'assets/img/cecinestpasunerue.png',
    'assets/img/favicon.ico',
    'assets/img/apple-touch-icon.png',
    'addresses.pmtiles',
    'search-index.json',
    'version.json',
]


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = {}
        self.canonical = None
        self.lang = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang')
        if tag in ('script', 'img') and a.get('src'):
            self.links.append(a['src'])
        if tag == 'link' and a.get('href'):
            if a.get('rel') == 'canonical':
                self.canonical = a['href']
            else:
                self.links.append(a['href'])
        if tag == 'meta' and a.get('property'):
            self.meta[a['property']] = a.get('content')


def parse(page_path):
    collector = LinkCollector()
    collector.feed(page_path.read_text(encoding='utf-8'))
    return collector


def is_local(url):
    parsed = urlparse(url)
    return not parsed.scheme and not parsed.netloc and not url.startswith(('#', 'data:'))


@pytest.mark.parametrize('page', PAGES)
def test_page_sans_balise_jinja(site_dir, page):
    text = (site_dir / page).read_text(encoding='utf-8')
    assert not re.search(r'\{\{|\{%|\{#', text)


@pytest.mark.parametrize('page', PAGES)
def test_langue_et_url_canonique(site_dir, page):
    doc = parse(site_dir / page)
    assert doc.lang == 'fr'
    assert doc.canonical == SITE_URL
    assert doc.meta.get('og:url') == SITE_URL


@pytest.mark.parametrize('page', PAGES)
def test_liens_locaux_existent(site_dir, page):
    doc = parse(site_dir / page)
    base = (site_dir / page).parent
    local = [link for link in doc.links if is_local(link)]
    assert local
    for link in local:
        assert (base / link).resolve().is_file(), link


def test_imports_js_existent(site_dir):
    for module in (site_dir / 'js').glob('*.js'):
        for target in re.findall(r"from '(\./[^']+)'", module.read_text(encoding='utf-8')):
            assert (module.parent / target).is_file(), f'{module.name} importe {target}'


def test_image_de_partage_publiee(site_dir):
    doc = parse(site_dir / 'index.html')
    image = doc.meta.get('og:image', '')
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
    for name in ('tests', 'node_modules', '.github', 'fetch-latest.py', 'build-site.py', 'README.md'):
        assert name not in published
