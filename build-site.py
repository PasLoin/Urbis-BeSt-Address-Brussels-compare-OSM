import argparse
import json
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
TEMPLATE = 'index.html.j2'
SITE_URL = 'https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/'
REFERENCE_LANG = 'fr'
LANGS = {
    'fr': {'path': '', 'og': 'fr_BE', 'name': 'Français'},
    'en': {'path': 'en/', 'og': 'en_GB', 'name': 'English'},
    'nl': {'path': 'nl/', 'og': 'nl_BE', 'name': 'Nederlands'},
}
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


def render_pages(out):
    env = Environment(
        loader=FileSystemLoader(ROOT / 'templates'),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
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
            canonical=SITE_URL + conf['path'],
            alternates=alternates,
            site_url=SITE_URL,
            t=lambda key: page_strings[key],
            dict_json=script_json(page_strings),
            banners_json=script_json(banners),
        ), encoding='utf-8')


def build(data_dir, out):
    missing = [name for name in DATA if not (data_dir / name).is_file()]
    if missing:
        sys.exit(f'[ERREUR] Données absentes de {data_dir} : {", ".join(missing)}. Lancer fetch-data.py.')
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    render_pages(out)
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
