import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(module_name, filename):
    path = REPO_ROOT / filename
    if not path.is_file():
        pytest.skip(f'{filename} introuvable à {path}')
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='session')
def tiles_mod():
    """Module generate-tiles.py chargé dynamiquement."""
    return _load_module('generate_tiles', 'generate-tiles.py')


@pytest.fixture(scope='session')
def assoc_mod():
    """Module compare-postal-codes-and-associetedStreet.py chargé dynamiquement."""
    return _load_module('compare_postal_codes', 'compare-postal-codes-and-associetedStreet.py')

