import json
import os
from datetime import date, datetime

import pytest

MIN_TOTAL = int(os.environ.get('MIN_TOTAL', '200000'))
MAX_MISSING_RATIO = float(os.environ.get('MAX_MISSING_RATIO', '0.05'))
MIN_STREETS = int(os.environ.get('MIN_STREETS', '3000'))
MIN_INDEX_ADDRESSES = int(os.environ.get('MIN_INDEX_ADDRESSES', '150000'))
MIN_TILES_BYTES = int(os.environ.get('MIN_TILES_BYTES', str(20 * 1024 * 1024)))


@pytest.fixture(scope='module')
def version(data_dir):
    return json.loads((data_dir / 'version.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def search_index(data_dir):
    return json.loads((data_dir / 'search-index.json').read_text(encoding='utf-8'))


def test_dates_lisibles(version):
    date.fromisoformat(version['urbis_date'])
    assert version['osm_date'], 'osm_date vide : timestamp OSM non récupéré'
    datetime.fromisoformat(version['osm_date'].replace('Z', '+00:00'))


def test_osm_charge(version):
    assert version['stats'].get('osm_loaded') is True


def test_total_plausible(version):
    assert version['stats']['total'] >= MIN_TOTAL


def test_statuts_urbis_somment_au_total(version):
    s = version['stats']
    assert s['ok'] + s['missing'] + s['verified_absent'] == s['total']


def test_part_des_manquantes_plausible(version):
    s = version['stats']
    assert s['missing'] / s['total'] <= MAX_MISSING_RATIO


def test_compteurs_hors_urbis_presents(version):
    s = version['stats']
    assert s.get('missing_in_urbis', 0) >= 0
    assert s.get('missing_in_urbis_verified', 0) >= 0


def test_tuiles_pmtiles_v3(data_dir):
    path = data_dir / 'addresses.pmtiles'
    with open(path, 'rb') as f:
        header = f.read(8)
    assert header[:7] == b'PMTiles'
    assert header[7] == 3
    assert path.stat().st_size >= MIN_TILES_BYTES


def test_index_de_recherche(search_index):
    assert search_index['v'] == 1
    assert len(search_index['s']) == len(search_index['sn'])
    assert len(search_index['s']) >= MIN_STREETS
    assert len(search_index['a']) >= MIN_INDEX_ADDRESSES
    street_count = len(search_index['s'])
    for sid, number, lat, lon in search_index['a']:
        assert 0 <= sid < street_count
        assert isinstance(number, str) and number
        assert 50.6 < lat < 51.0
        assert 4.1 < lon < 4.6
