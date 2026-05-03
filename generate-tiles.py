#!/usr/bin/env python3
import sys
import os
import re
import subprocess
import tempfile
import unicodedata
import json
import pandas as pd
import geopandas as gpd
import osmium
from shapely.geometry import Point, shape
from shapely.prepared import prep
import urllib.request

PBF_FILE = 'brussels_capital_region-latest.osm.pbf'
BOUNDARY_RELATION = 54094
BOUNDARY_URL = f'https://polygons.openstreetmap.fr/get_geojson.py?id={BOUNDARY_RELATION}&params=0'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}

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
        # For reverse lookup: store details of OSM addresses with coordinates
        self.address_details = {}  # (norm_street, norm_nbr) -> {'street': raw, 'nbr': raw, 'lat': float, 'lon': float}

    def _collect_street_variants(self, tags):
        variants = set()
        for tag in STREET_NAME_TAGS:
            val = tags.get(tag)
            if val:
                for part in split_bilingual(val):
                    variants.add(part)
        if len(variants) > 1:
            self.street_name_groups.append(variants)

    def _collect_verified_absent(self, prefix, tags):
        """Collect verified-absent addresses from not:addr:* or was:addr:* tags."""
        nbr_tag = tags.get(f'{prefix}:addr:housenumber')
        street_tags = [
            tags.get(f'{prefix}:addr:street'),
        ]
        if nbr_tag:
            nbrs = [normalize(n) for n in nbr_tag.split(';')]
            for raw_street in street_tags:
                if not raw_street:
                    continue
                parts = split_bilingual(raw_street)
                for part in parts:
                    for nbr in nbrs:
                        self.verified_absent.add((part, nbr.strip()))

    def _process(self, tags, lat=None, lon=None):
        housenumber = tags.get('addr:housenumber')
        street_tags = [
            tags.get('addr:street'),
            tags.get('addr:street_official'),
            tags.get('addr:place'),
        ]
        if housenumber:
            nbrs_raw = [n.strip() for n in housenumber.split(';')]
            for raw_street in street_tags:
                if not raw_street:
                    continue
                parts = split_bilingual(raw_street)
                for part in parts:
                    for nbr_raw in nbrs_raw:
                        nbr_n = normalize(nbr_raw)
                        self.addresses.add((part, nbr_n))
                        # Store details for reverse lookup (keep first occurrence)
                        if lat is not None and lon is not None:
                            key = (part, nbr_n)
                            if key not in self.address_details:
                                self.address_details[key] = {
                                    'street': raw_street,
                                    'nbr': nbr_raw,
                                    'lat': lat,
                                    'lon': lon,
                                }

        # Handle both not:addr:* and was:addr:* as verified absent
        for prefix in ('not', 'was'):
            self._collect_verified_absent(prefix, tags)

    def node(self, n):
        lat, lon = None, None
        if n.location.valid():
            lat, lon = n.location.lat, n.location.lon
        self._process(n.tags, lat, lon)

    def way(self, w):
        lat, lon = None, None
        # Compute centroid only if the way carries an address
        if w.tags.get('addr:housenumber'):
            try:
                lats, lons = [], []
                for nd in w.nodes:
                    if nd.location.valid():
                        lats.append(nd.location.lat)
                        lons.append(nd.location.lon)
                if lats:
                    lat = sum(lats) / len(lats)
                    lon = sum(lons) / len(lons)
            except Exception:
                pass
        self._process(w.tags, lat, lon)
        if w.tags.get('highway'):
            self._collect_street_variants(w.tags)

    def relation(self, r):
        # Relations rarely carry addr:* directly; skip coordinates for them
        self._process(r.tags)
        if r.tags.get('type') == 'associatedStreet':
            self._collect_street_variants(r.tags)

def load_boundary():
    """Download the Brussels-Capital Region boundary polygon (relation/54094)."""
    print(f'[BOUNDARY] Téléchargement de la frontière (relation/{BOUNDARY_RELATION})...')
    try:
        req = urllib.request.Request(BOUNDARY_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        geom = shape(data)
        prepared = prep(geom)
        print(f'[BOUNDARY] Polygone chargé ({geom.geom_type}, {geom.area:.6f}°²)')
        return prepared
    except Exception as e:
        print(f'[WARN] Impossible de charger la frontière : {e}')
        return None

def load_osm(pbf_path):
    print(f'[OSM] Lecture de {pbf_path}...')
    handler = AddressHandler()
    handler.apply_file(pbf_path, locations=True)
    alias_map = {}
    for group in handler.street_name_groups:
        for name in group:
            alias_map.setdefault(name, set()).update(group - {name})
    return handler.addresses, handler.verified_absent, alias_map, handler.address_details

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
    if any((s, nbr_n) in verified_absent for s in expanded): return 'verified_absent'
    return 'missing'

def find_osm_only(gdf, osm_addrs, osm_details, alias_map, boundary=None):
    """Find OSM addresses that have no match in the UrbIS dataset."""
    # Build expanded UrbIS address set
    urbis_set = set()
    for _, row in gdf.iterrows():
        nbr = normalize(str(row['POLICENUM'])) if row['POLICENUM'] else ''
        if not nbr:
            continue
        streets = set()
        for col in ('STRNAMEFRE', 'STRNAMEDUT'):
            val = row.get(col)
            if val:
                n = normalize(val)
                streets.add(n)
                streets.update(alias_map.get(n, set()))
        for s in streets:
            urbis_set.add((s, nbr))

    # Find OSM addresses not in UrbIS
    osm_only = []
    skipped_boundary = 0
    for (norm_street, norm_nbr), detail in osm_details.items():
        # Filter by Brussels boundary
        if boundary is not None:
            if not boundary.contains(Point(detail['lon'], detail['lat'])):
                skipped_boundary += 1
                continue
        # Expand with aliases
        candidates = {norm_street}
        candidates.update(alias_map.get(norm_street, set()))
        if any((s, norm_nbr) in urbis_set for s in candidates):
            continue
        osm_only.append(detail)

    if boundary is not None:
        print(f'[REVERSE] {skipped_boundary} adresses OSM hors Région exclues')
    print(f'[REVERSE] {len(osm_only)} adresses OSM absentes d\'UrbIS')
    return osm_only

def gpkg_to_pmtiles(gpkg_path, pmtiles_path, pbf_path=None):
    osm_addrs, verified_absent, alias_map, osm_details = set(), set(), {}, {}
    osm_loaded = False
    if pbf_path and os.path.isfile(pbf_path):
        osm_addrs, verified_absent, alias_map, osm_details = load_osm(pbf_path)
        osm_loaded = True
        print(f'[OSM] {len(osm_addrs)} adresses, {len(verified_absent)} vérifiées absentes, {len(osm_details)} avec coordonnées')
    else:
        print(f'[WARN] Fichier PBF introuvable ({pbf_path}), pas de croisement OSM')

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

    # Reverse matching: find OSM addresses missing from UrbIS
    osm_only_count = 0
    if osm_loaded:
        boundary = load_boundary()
        osm_only = find_osm_only(gdf, osm_addrs, osm_details, alias_map, boundary)
        osm_only_count = len(osm_only)
        if osm_only:
            rows = []
            for d in osm_only:
                rows.append({
                    'STRNAMEFRE': d['street'],
                    'STRNAMEDUT': None,
                    'POLICENUM': d['nbr'],
                    'ZIPCODE': None,
                    'MUNNAMEFRE': None,
                    'MUNNAMEDUT': None,
                    'INSPIRE_ID': None,
                    'PARENTID': None,
                    'status': 'missing_in_urbis',
                    'geometry': Point(d['lon'], d['lat']),
                })
            osm_only_gdf = gpd.GeoDataFrame(rows, geometry='geometry', crs='EPSG:4326')
            print(f'[REVERSE] osm_only_gdf: {len(osm_only_gdf)} lignes, geom_type: {osm_only_gdf.geometry.geom_type.unique()}')
            combined = pd.concat([gdf, osm_only_gdf], ignore_index=True)
            gdf = gpd.GeoDataFrame(combined, geometry='geometry', crs='EPSG:4326')
            # Sanity check
            null_geom = gdf.geometry.isna().sum()
            if null_geom > 0:
                print(f'[WARN] {null_geom} features sans géométrie, supprimées')
                gdf = gdf[gdf.geometry.notna()].copy()

    # Compute coverage statistics
    counts = gdf['status'].value_counts().to_dict()
    urbis_total = int(counts.get('ok', 0)) + int(counts.get('missing', 0)) + int(counts.get('verified_absent', 0))
    stats = {
        'total': urbis_total,
        'ok': int(counts.get('ok', 0)),
        'missing': int(counts.get('missing', 0)),
        'verified_absent': int(counts.get('verified_absent', 0)),
        'missing_in_urbis': int(counts.get('missing_in_urbis', 0)),
        'osm_loaded': osm_loaded,
    }
    stats_path = os.path.join(os.path.dirname(pmtiles_path) or '.', 'stats.json')
    with open(stats_path, 'w') as f:
        json.dump(stats, f)
    print(f'[STATS] {stats}')

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
