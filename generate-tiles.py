#!/usr/bin/env python3
import sys
import os
import re
import subprocess
import tempfile
import unicodedata
import json
import math
from collections import defaultdict
import pandas as pd
import geopandas as gpd
import osmium
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep
import urllib.request

PBF_FILE = 'brussels_capital_region-latest.osm.pbf'
BOUNDARY_RELATION = 54094
BOUNDARY_URL = f'https://raw.githubusercontent.com/PasLoin/Osm-python-analyse_Belgium/main/pbf_analyse/{BOUNDARY_RELATION}.poly'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}
MAX_MATCH_DIST_M = 500

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
        self.address_coords = defaultdict(list)
        self.osm_objects = []

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

    def _process(self, tags, lat=None, lon=None, osm_ref=None):
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
                        if lat is not None and lon is not None:
                            self.address_coords[(part, nbr_n)].append((lat, lon))

            streets = [s for s in street_tags if s]
            if streets and osm_ref and lat is not None and lon is not None:
                for nbr_raw in nbrs_raw:
                    if nbr_raw:
                        self.osm_objects.append({
                            'osm': osm_ref,
                            'streets': streets,
                            'nbr': nbr_raw,
                            'note': tags.get('note', ''),
                            'lat': lat,
                            'lon': lon,
                        })

        # Handle both not:addr:* and was:addr:* as verified absent
        for prefix in ('not', 'was'):
            self._collect_verified_absent(prefix, tags)

    def node(self, n):
        lat, lon = None, None
        if n.location.valid():
            lat, lon = n.location.lat, n.location.lon
        self._process(n.tags, lat, lon, f'node/{n.id}')

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
        self._process(w.tags, lat, lon, f'way/{w.id}')
        if w.tags.get('highway'):
            self._collect_street_variants(w.tags)

    def relation(self, r):
        # Relations rarely carry addr:* directly; skip coordinates for them
        self._process(r.tags)
        if r.tags.get('type') == 'associatedStreet':
            self._collect_street_variants(r.tags)

def parse_poly(text):
    """Parse an Osmosis .poly file into a (Multi)Polygon."""
    outers, holes = [], []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 1
    while i < len(lines) and lines[i] != 'END':
        is_hole = lines[i].startswith('!')
        i += 1
        ring = []
        while i < len(lines) and lines[i] != 'END':
            x, y = lines[i].split()[:2]
            ring.append((float(x), float(y)))
            i += 1
        i += 1
        if len(ring) >= 3:
            (holes if is_hole else outers).append(Polygon(ring).buffer(0))
    if not outers:
        raise ValueError('aucun anneau extérieur dans le fichier .poly')
    geom = unary_union(outers)
    if holes:
        geom = geom.difference(unary_union(holes))
    return geom

def load_boundary():
    """Download the Brussels-Capital Region boundary polygon (relation/54094)."""
    print(f'[BOUNDARY] Téléchargement de la frontière (relation/{BOUNDARY_RELATION}) : {BOUNDARY_URL}')
    try:
        req = urllib.request.Request(BOUNDARY_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            geom = parse_poly(r.read().decode('utf-8'))
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
    return (handler.addresses, handler.verified_absent, alias_map,
            handler.osm_objects, handler.address_coords)

def _dist_m(lat1, lon1, lat2, lon2):
    x = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    y = (lat2 - lat1) * 111320
    return math.hypot(x, y)

def get_status(streetfr, streetnl, nbr, osm_addrs, verified_absent, alias_map,
               osm_coords=None, lat=None, lon=None):
    if not nbr: return 'missing'
    nbr_n = normalize(nbr)
    base = set()
    if streetfr: base.add(normalize(streetfr))
    if streetnl: base.add(normalize(streetnl))
    expanded = set(base)
    for s in base:
        expanded.update(alias_map.get(s, set()))
    matched = [(s, nbr_n) for s in expanded if (s, nbr_n) in osm_addrs]
    if matched:
        if osm_coords is None or lat is None or lon is None:
            return 'ok'
        positions = [p for k in matched for p in osm_coords.get(k, ())]
        if not positions:
            return 'ok'
        if any(_dist_m(lat, lon, plat, plon) <= MAX_MATCH_DIST_M for plat, plon in positions):
            return 'ok'
    if any((s, nbr_n) in verified_absent for s in expanded): return 'verified_absent'
    return 'missing'

def find_osm_only(gdf, osm_objects, alias_map, boundary=None):
    """Find OSM addresses that have no match in the UrbIS dataset."""
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

    osm_only = []
    seen = set()
    skipped_boundary = 0
    for obj in osm_objects:
        key = (obj['osm'], normalize(obj['nbr']))
        if key in seen:
            continue
        seen.add(key)
        if boundary is not None and not boundary.contains(Point(obj['lon'], obj['lat'])):
            skipped_boundary += 1
            continue
        nbr_n = key[1]
        candidates = set()
        for raw_street in obj['streets']:
            for part in split_bilingual(raw_street):
                candidates.add(part)
                candidates.update(alias_map.get(part, set()))
        if any((s, nbr_n) in urbis_set for s in candidates):
            continue
        osm_only.append({**obj, 'street': obj['streets'][0]})

    if boundary is not None:
        print(f'[REVERSE] {skipped_boundary} adresses OSM hors Région exclues')
    print(f'[REVERSE] {len(osm_only)} adresses OSM absentes d\'UrbIS')
    return osm_only

def osm_only_status(note):
    return 'missing_in_urbis_verified' if 'urbis' in (note or '').lower() else 'missing_in_urbis'

def export_osm_only(osm_only, out_dir):
    columns = ['rue_osm', 'rue_fr', 'rue_nl', 'numero', 'statut', 'note_osm', 'objet_osm', 'lien_osm', 'lon', 'lat']
    rows = []
    for d in osm_only:
        parts = re.split(r' [-\u2013\u2014] ', d['street'], maxsplit=1)
        fr, nl = (parts + [''])[:2]
        rows.append({
            'rue_osm': d['street'],
            'rue_fr': fr.strip(),
            'rue_nl': nl.strip(),
            'numero': d['nbr'],
            'statut': osm_only_status(d.get('note')),
            'note_osm': d.get('note', '') or '',
            'objet_osm': d['osm'],
            'lien_osm': f"https://www.openstreetmap.org/{d['osm']}",
            'lon': round(d['lon'], 7),
            'lat': round(d['lat'], 7),
        })
    out = gpd.GeoDataFrame(
        pd.DataFrame(rows, columns=columns),
        geometry=gpd.points_from_xy([r['lon'] for r in rows], [r['lat'] for r in rows]),
        crs='EPSG:4326',
    ).to_crs('EPSG:31370')
    out = out.sort_values(
        ['rue_osm', 'numero', 'objet_osm'],
        key=lambda col: col.astype(str).str.lower(),
    ).reset_index(drop=True)
    csv_path = os.path.join(out_dir, 'osm-absent-urbis.csv')
    gpkg_path = os.path.join(out_dir, 'osm-absent-urbis.gpkg')
    out.drop(columns='geometry').to_csv(csv_path, index=False, encoding='utf-8-sig')
    if os.path.exists(gpkg_path):
        os.remove(gpkg_path)
    out.to_file(gpkg_path, layer='osm_absent_urbis', driver='GPKG')
    print(f'[EXPORT] {len(out)} adresses OSM absentes d\'UrbIS -> {csv_path}, {gpkg_path}')
    return csv_path, gpkg_path

def gpkg_to_pmtiles(gpkg_path, pmtiles_path, pbf_path=None):
    osm_addrs, verified_absent, alias_map, osm_objects, osm_coords = set(), set(), {}, [], {}
    osm_loaded = False
    if pbf_path and os.path.isfile(pbf_path):
        osm_addrs, verified_absent, alias_map, osm_objects, osm_coords = load_osm(pbf_path)
        osm_loaded = True
        print(f'[OSM] {len(osm_addrs)} adresses, {len(verified_absent)} vérifiées absentes, {len(osm_objects)} objets avec coordonnées')
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
            osm_addrs, verified_absent, alias_map,
            osm_coords,
            row.geometry.y if row.geometry is not None and not row.geometry.is_empty else None,
            row.geometry.x if row.geometry is not None and not row.geometry.is_empty else None,
        ), axis=1
    )

    # Reverse matching: find OSM addresses missing from UrbIS
    osm_only_count = 0
    if osm_loaded:
        boundary = load_boundary()
        if boundary is None:
            print('[WARN] Reverse matching ignoré : frontière indisponible')
        else:
            osm_only = find_osm_only(gdf, osm_objects, alias_map, boundary)
            osm_only_count = len(osm_only)
            export_osm_only(osm_only, os.path.dirname(pmtiles_path) or '.')
            if osm_only:
                rows = []
                for d in osm_only:
                    status = osm_only_status(d.get('note'))
                    rows.append({
                        'STRNAMEFRE': d['street'],
                        'STRNAMEDUT': None,
                        'POLICENUM': d['nbr'],
                        'ZIPCODE': None,
                        'MUNNAMEFRE': None,
                        'MUNNAMEDUT': None,
                        'INSPIRE_ID': None,
                        'PARENTID': None,
                        'status': status,
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
        'missing_in_urbis_verified': int(counts.get('missing_in_urbis_verified', 0)),
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
