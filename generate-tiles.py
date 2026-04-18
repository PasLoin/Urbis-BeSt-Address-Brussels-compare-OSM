#!/usr/bin/env python3
import sys
import os
import re
import subprocess
import tempfile
import unicodedata
import geopandas as gpd
import osmium

PBF_FILE = 'brussels_capital_region-latest.osm.pbf'

def normalize(s):
    if not s: return ''
    s = s.strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = ' '.join(s.split())
    return s

def split_bilingual(s):
    s = normalize(s)
    return [p for p in re.split(r' [-\u2013\u2014] ', s) if p]

STREET_NAME_TAGS = [
    'name', 'alt_name', 'alt_name:fr', 'alt_name:nl',
    'official_name', 'official_name:fr', 'official_name:nl',
    'not:name', 'old_name', 'name:left', 'name:right',
]

class AddressHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.addresses = set()
        self.verified_absent = set()
        self.street_name_groups = []

    def _collect_street_variants(self, tags):
        variants = set()
        for tag in STREET_NAME_TAGS:
            val = tags.get(tag)
            if val:
                for part in split_bilingual(val):
                    variants.add(part)
        if len(variants) > 1:
            self.street_name_groups.append(variants)

    def _process(self, tags):
        housenumber = tags.get('addr:housenumber')
        street_tags = [
            tags.get('addr:street'),
            tags.get('addr:street_official'),
            tags.get('addr:place'),
        ]
        if housenumber:
            nbrs = [normalize(n) for n in housenumber.split(';')]
            for raw_street in street_tags:
                if not raw_street:
                    continue
                parts = split_bilingual(raw_street)
                for part in parts:
                    for nbr in nbrs:
                        self.addresses.add((part, nbr.strip()))

        not_nbr = tags.get('not:addr:housenumber')
        not_street_tags = [
            tags.get('not:addr:street'),
        ]
        if not_nbr:
            nbrs = [normalize(n) for n in not_nbr.split(';')]
            for raw_street in not_street_tags:
                if not raw_street:
                    continue
                parts = split_bilingual(raw_street)
                for part in parts:
                    for nbr in nbrs:
                        self.verified_absent.add((part, nbr.strip()))

    def node(self, n): self._process(n.tags)

    def way(self, w):
        self._process(w.tags)
        if w.tags.get('highway'):
            self._collect_street_variants(w.tags)

    def relation(self, r):
        self._process(r.tags)
        if r.tags.get('type') == 'associatedStreet':
            self._collect_street_variants(r.tags)

def load_osm(pbf_path):
    print(f'[OSM] Lecture de {pbf_path}...')
    handler = AddressHandler()
    handler.apply_file(pbf_path, locations=False)
    alias_map = {}
    for group in handler.street_name_groups:
        for name in group:
            alias_map.setdefault(name, set()).update(group - {name})
    return handler.addresses, handler.verified_absent, alias_map

def get_status(streetfr, streetnl, nbr, osm_addrs, verified_absent, alias_map):
    if not nbr: return 'missing'
    nbr_n = normalize(nbr)
    base = set()
    if streetfr: base.add(normalize(streetfr))
    if streetnl: base.add(normalize(streetnl))
    expanded = set(base)
    for s in base:
        expanded.update(alias_map.get(s, set()))
    if any((s, nbr_n) in osm_addrs for s in expanded): return 'ok'
    if any((s, nbr_n) in verified_absent for s in base): return 'verified_absent'
    return 'missing'

def gpkg_to_pmtiles(gpkg_path, pmtiles_path, pbf_path=None):
    osm_addrs, verified_absent, alias_map = set(), set(), {}
    if pbf_path and os.path.isfile(pbf_path):
        osm_addrs, verified_absent, alias_map = load_osm(pbf_path)

    print(f'[GEO] Lecture de {gpkg_path}...')
    gdf = gpd.read_file(gpkg_path, layer='Addresses')

    print(f'[GEO] Reprojection vers WGS84...')
    gdf = gdf.to_crs('EPSG:4326')
    gdf = gdf[gdf['PARENTID'].isna()].copy()

    print('[GEO] Calcul du statut OSM...')
    gdf['status'] = gdf.apply(
        lambda row: get_status(
            row['STRNAMEFRE'], row['STRNAMEDUT'], row['POLICENUM'],
            osm_addrs, verified_absent, alias_map
        ), axis=1
    )

    columns_to_keep = [
        'STRNAMEFRE', 'STRNAMEDUT', 'POLICENUM', 'ZIPCODE',
        'MUNNAMEFRE', 'MUNNAMEDUT', 'status', 'INSPIRE_ID', 'PARENTID', 'geometry'
    ]
    existing_cols = [c for c in columns_to_keep if c in gdf.columns]
    gdf = gdf[existing_cols]

    with tempfile.NamedTemporaryFile(suffix='.geojson', delete=False) as f:
        tmp_geojson = f.name
    gdf.to_file(tmp_geojson, driver='GeoJSON')

    print(f'[TILES] Génération de {pmtiles_path}...')
    cmd = [
        'tippecanoe',
        '--output=' + pmtiles_path,
        '--force',
        '--minimum-zoom=10',
        '--maximum-zoom=19',
        '--layer=addresses',
        '--no-feature-limit',
        '--no-tile-size-limit',
        '--drop-rate=0',
        '--base-zoom=19',
        '--no-line-simplification',
        '--preserve-input-order',
        tmp_geojson
    ]
    subprocess.run(cmd, check=True, capture_output=False)
    os.unlink(tmp_geojson)

    size_mb = os.path.getsize(pmtiles_path) / 1024 / 1024
    print(f'[OK] PMTiles généré : {pmtiles_path} ({size_mb:.1f} MB)')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: ./generate-tiles.py fichier.gpkg [output.pmtiles] [osm.pbf]')
        sys.exit(1)
    gpkg_path    = sys.argv[1]
    pmtiles_path = sys.argv[2] if len(sys.argv) > 2 else 'addresses.pmtiles'
    pbf_path     = sys.argv[3] if len(sys.argv) > 3 else PBF_FILE
    gpkg_to_pmtiles(gpkg_path, pmtiles_path, pbf_path)
