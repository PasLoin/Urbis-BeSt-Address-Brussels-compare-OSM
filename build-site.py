import argparse
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent
TEMPLATE = 'index.html'
SITE_URL = 'https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/'
LANGS = {
    'fr': {'path': '', 'og': 'fr_BE'},
}
STATIC = ['js', 'assets', 'style.css', 'taginfo.json']
DATA = ['addresses.pmtiles', 'search-index.json', 'version.json']


def copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def render_pages(out):
    env = Environment(
        loader=FileSystemLoader(ROOT),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE)
    alternates = [{'lang': lang, 'path': conf['path']} for lang, conf in LANGS.items()]
    for lang, conf in LANGS.items():
        page = out / conf['path'] / 'index.html'
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(template.render(
            lang=lang,
            path=conf['path'],
            root='../' * conf['path'].count('/'),
            og_locale=conf['og'],
            alternates=alternates,
            site_url=SITE_URL,
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
    print(f'[OK] Site généré dans {out}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Génère le site statique dans un dossier de sortie.')
    parser.add_argument('--data', default='data', help='dossier contenant les fichiers de données')
    parser.add_argument('--out', default='_site', help='dossier de sortie')
    args = parser.parse_args()
    build(Path(args.data).resolve(), Path(args.out).resolve())
