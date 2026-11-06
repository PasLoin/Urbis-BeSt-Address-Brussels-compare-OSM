import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_build_site():
    spec = importlib.util.spec_from_file_location('build_site', ROOT / 'build-site.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_build_site = _load_build_site()
LANGS = _build_site.LANGS
REFERENCE_LANG = _build_site.REFERENCE_LANG
SITE_URL = _build_site.SITE_URL
