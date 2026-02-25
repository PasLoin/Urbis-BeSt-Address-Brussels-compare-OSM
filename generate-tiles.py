#!/usr/bin/env python3
import sys
import os
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

class AddressHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.addresses = set()
        self.verified_absent = set()

    def _process(self, tags):
        housenumber = tags.get('addr:housenumber')
        street = tags.get('addr:street')
        if housenumber and street:
            nbrs = [normalize(n) for n in housenumber.split(';')]
            parts = [normalize(p) for p in street.split(' - ')]
            for part in parts:
                for nbr in nbrs:
                    self.addresses.add((part, nbr.strip()))

        not_nbr = tags.get('not:addr:housenumber')
        not_street = tags.get('not:addr:street')
        if not_nbr and not_street:
            nbrs = [normalize(n) for n in not_nbr.split(';')]
            parts = [normalize(p) for p in not_street.split(' - ')]
            for part in parts:
                for nbr in nbrs:
                    self.verified_absent.add((part, nbr.strip()))

    def node(self, n): self._process(n.tags)
    def way(self, w): self._process(w.tags)
    def relation(self, r): self._process(r.tags)

def load_osm(pbf_path):
    print(f'[OSM] Lecture de {pbf_path}...')
    handler = AddressHandler()
    handler.apply_file(pbf_path, locations=False)
    return handler.addresses, handler.verified_absent

def get_status(streetfr, streetnl, nbr, osm_addrs, verified_absent):
    if not nbr: return 'missing'
    nbr_n = normalize(nbr)
    keys = []
    if streetfr: keys.append((normalize(streetfr), nbr_n))
    if streetnl: keys.append((normalize(streetnl), nbr_n))
    if any(k in osm_addrs for k in keys): return 'ok'
    if any(k in verified_absent for k in keys): return 'verified_absent'
    return 'missing'

def gpkg_to_pmtiles(gpkg_path, pmtiles_path, pbf_path=None):
    osm_addrs, verified_absent = set(), set()
    if pbf_path and os.path.isfile(pbf_path):
        osm_addrs, verified_absent = load_osm(pbf_path)

    print(f'[GEO] Lecture de {gpkg_path}...')
    gdf = gpd.read_file(gpkg_path, layer='Addresses')

    print(f'[GEO] Reprojection vers WGS84...')
    gdf = gdf.to_crs('EPSG:4326')
    gdf = gdf[gdf['PARENTID'].isna()].copy()

    print('[GEO] Calcul du statut OSM...')
    gdf['status'] = gdf.apply(
        lambda row: get_status(
            row['STRNAMEFRE'], row['STRNAMEDUT'], row['POLICENUM'],
            osm_addrs, verified_absent
        ), axis=1
    )

    columns_to_keep = [
        'STRNAMEFRE', 'STRNAMEDUT', 'POLICENUM', 'ZIPCODE',
        'MUNNAMEFRE', 'MUNNAMEDUT', 'status', 'INSPIRE_ID', 'PARENTID', 'BU_ID', 'geometry'
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
