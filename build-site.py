import argparse
import json
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
TEMPLATE = 'index.html.j2'
NOT_FOUND_TEMPLATE = '404.html.j2'
SITE_URL = 'https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/'
LANGUAGES_FILE = ROOT / 'i18n' / 'languages.json'
LANGUAGES = json.loads(LANGUAGES_FILE.read_text(encoding='utf-8'))
REFERENCE_LANG = LANGUAGES['reference']
TIME_ZONE = LANGUAGES['timeZone']
LANGS = LANGUAGES['languages']
BANNER_KEYS = {'text': 'banner.text', 'switch': 'banner.switch', 'dismiss': 'banner.dismiss'}
STATIC = ['js', 'assets', 'style.css', 'taginfo.json']
DATA = ['addresses.pmtiles', 'search-index.json', 'version.json']


def load_dict(lang):
    return json.loads((ROOT / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))


def load_strings(lang):
    return {**load_dict(REFERENCE_LANG), **load_dict(lang)}


def script_json(data):
    return Markup(json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))


def copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def environment():
    return Environment(
        loader=FileSystemLoader(ROOT / 'templates'),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render_pages(out):
    env = environment()
    template = env.get_template(TEMPLATE)
    strings = {lang: load_strings(lang) for lang in LANGS}
    alternates = [
        {'lang': lang, 'path': conf['path'], 'og': conf['og'], 'name': conf['name']}
        for lang, conf in LANGS.items()
    ]
    banners = {
        lang: {field: strings[lang][key] for field, key in BANNER_KEYS.items()}
        for lang in LANGS
    }
    for lang, conf in LANGS.items():
        page_strings = strings[lang]
        page = out / conf['path'] / 'index.html'
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(template.render(
            lang=lang,
            is_root=conf['path'] == '',
            root='../' * conf['path'].count('/'),
            og_locale=conf['og'],
            locale=conf['locale'],
            data_lang=conf['data'],
            time_zone=TIME_ZONE,
            canonical=SITE_URL + conf['path'],
            alternates=alternates,
            site_url=SITE_URL,
            t=lambda key: page_strings[key],
            dict_json=script_json(page_strings),
            banners_json=script_json(banners),
        ), encoding='utf-8')


def render_not_found(out):
    template = environment().get_template(NOT_FOUND_TEMPLATE)
    strings = {lang: load_strings(lang) for lang in LANGS}
    pages = [
        {'lang': lang, 'url': SITE_URL + conf['path'], 't': strings[lang].__getitem__}
        for lang, conf in LANGS.items()
    ]
    (out / '404.html').write_text(template.render(
        reference_lang=REFERENCE_LANG,
        site_name=strings[REFERENCE_LANG]['meta.siteName'],
        site_url=SITE_URL,
        pages=pages,
    ), encoding='utf-8')


def last_modified(data_dir):
    try:
        version = json.loads((data_dir / 'version.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    date = version.get('osm_date') or version.get('urbis_date')
    return date[:10] if isinstance(date, str) and len(date) >= 10 else None


def render_sitemap(out, lastmod=None):
    alternates = [(lang, SITE_URL + conf['path']) for lang, conf in LANGS.items()]
    alternates.append(('x-default', SITE_URL))
    links = ''.join(
        f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{escape(url)}"/>\n'
        for lang, url in alternates
    )
    modified = f'    <lastmod>{lastmod}</lastmod>\n' if lastmod else ''
    urls = ''.join(
        f'  <url>\n    <loc>{escape(SITE_URL + conf["path"])}</loc>\n{modified}{links}  </url>\n'
        for conf in LANGS.values()
    )
    (out / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        f'{urls}</urlset>\n',
        encoding='utf-8',
    )


def build(data_dir, out):
    missing = [name for name in DATA if not (data_dir / name).is_file()]
    if missing:
        sys.exit(f'[ERREUR] Données absentes de {data_dir} : {", ".join(missing)}. Lancer fetch-data.py.')
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    render_pages(out)
    render_not_found(out)
    render_sitemap(out, last_modified(data_dir))
    for name in STATIC:
        copy(ROOT / name, out / name)
    for name in DATA:
        copy(data_dir / name, out / name)
    print(f'[OK] Site généré dans {out} : {", ".join(LANGS)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Génère le site statique dans un dossier de sortie.')
    parser.add_argument('--data', default='data', help='dossier contenant les fichiers de données')
    parser.add_argument('--out', default='_site', help='dossier de sortie')
    args = parser.parse_args()
    build(Path(args.data).resolve(), Path(args.out).resolve())
