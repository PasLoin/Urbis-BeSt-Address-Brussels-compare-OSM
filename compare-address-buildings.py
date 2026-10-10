#!/usr/bin/env python3
import argparse
import csv
import glob
import importlib.util
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import date, datetime

import geopandas as gpd
import numpy as np
import osmium
import shapely
from osmium.geom import WKBFactory
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except AttributeError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REGION_POLY_URL = ('https://raw.githubusercontent.com/PasLoin/'
                   'Osm-python-analyse_Belgium/main/pbf_analyse/54094.poly')
REGION_POLY_CACHE = 'region_54094.poly'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}
GEOJSON_DIR = 'wrong_building_geojson'

TO_L72 = Transformer.from_crs('EPSG:4326', 'EPSG:31370', always_xy=True)
TO_WGS = Transformer.from_crs('EPSG:31370', 'EPSG:4326', always_xy=True)

STREET_NAME_TAGS = [
    'name', 'name:fr', 'name:nl', 'alt_name', 'alt_name:fr', 'alt_name:nl',
    'official_name', 'official_name:fr', 'official_name:nl',
    'old_name', 'name:left', 'name:right',
]

CATEGORY_LABELS = {
    'mauvais_batiment': 'ADRESSE SUR UN AUTRE BÂTIMENT QUE CELUI D\'URBIS',
    'eloigne': 'ADRESSE HORS BÂTIMENT ET ÉLOIGNÉE DU BÂTIMENT URBIS',
    'ambigu': 'CHEVAUCHEMENT AMBIGU (À VÉRIFIER)',
}


def normalize(s):
    if not s:
        return ''
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.split())


def norm_nbr(s):
    return re.sub(r'\s+', '', normalize(s))


def split_bilingual(s):
    s = normalize(s)
    return [p for p in re.split(r' [-\u2013\u2014] ', s) if p]


def nat_key(s):
    m = re.match(r'\s*(\d+)(.*)', str(s))
    return (int(m.group(1)), m.group(2).strip().lower()) if m else (10 ** 9, str(s).lower())


def find_col(gdf, *names):
    lower = {c.lower(): c for c in gdf.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def is_blank(v):
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return str(v).strip() == '' or str(v).strip().lower() in ('nan', 'none')


def id_keys(v):
    if is_blank(v):
        return []
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    segments = [seg for seg in re.split(r'[/#:]', s) if seg]
    keys = [s] + segments[::-1]
    for seg in segments[::-1]:
        for digits in re.findall(r'\d+', seg):
            keys.append('#' + str(int(digits)))
    return list(dict.fromkeys(keys))


def polygonal(g):
    if g is None or g.is_empty:
        return None
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    if g.geom_type == 'GeometryCollection':
        parts = [p for p in g.geoms if p.geom_type in ('Polygon', 'MultiPolygon') and not p.is_empty]
        return unary_union(parts) if parts else None
    return None


def transform_array(geoms, transformer):
    arr = np.empty(len(geoms), dtype=object)
    arr[:] = geoms
    return shapely.transform(
        arr, lambda c: np.column_stack(transformer.transform(c[:, 0], c[:, 1])))


def to_wgs(g):
    return transform_array([g], TO_WGS)[0]


def load_fetch_module():
    path = os.path.join(HERE, 'fetch-latest.py')
    spec = importlib.util.spec_from_file_location('fetch_latest', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_inputs(args):
    fl = None
    pbf = args.pbf
    if not os.path.isfile(pbf):
        fl = fl or load_fetch_module()
        fl.download_osm_pbf()
        pbf = fl.OSM_PBF_FILE
    gpkg = args.gpkg
    urbis_date = 'inconnue'
    if gpkg and os.path.isfile(gpkg):
        m = re.search(r'(\d{8})', gpkg)
        if m:
            urbis_date = f'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}'
        return pbf, gpkg, urbis_date
    fl = fl or load_fetch_module()
    latest_dt, latest_url = fl.find_latest_gpkg(fl.FEED_URL)
    zip_name = os.path.basename(latest_url)
    if not os.path.isfile(zip_name):
        fl.download(latest_url, zip_name)
    gpkg = fl.extract_gpkg(zip_name)
    return pbf, gpkg, str(latest_dt.date())


def load_region():
    if os.path.isfile(REGION_POLY_CACHE):
        with open(REGION_POLY_CACHE, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        print(f'[REGION] Téléchargement : {REGION_POLY_URL}')
        req = urllib.request.Request(REGION_POLY_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode('utf-8', errors='replace')
        with open(REGION_POLY_CACHE, 'w', encoding='utf-8') as f:
            f.write(text)
    outers, holes, cur, hole = [], [], None, False
    lines = [l.strip() for l in text.splitlines() if l.strip()][1:]
    for line in lines:
        if cur is None:
            if line == 'END':
                break
            hole = line.startswith('!')
            cur = []
        elif line == 'END':
            if len(cur) >= 3:
                (holes if hole else outers).append(shapely.make_valid(Polygon(cur)))
            cur = None
        else:
            parts = line.split()
            if len(parts) >= 2:
                cur.append((float(parts[0]), float(parts[1])))
    geom = unary_union(outers)
    if holes:
        geom = geom.difference(unary_union(holes))
    print(f'[REGION] Polygone chargé ({geom.geom_type})')
    return geom


def load_urbis(gpkg):
    print(f'[URBIS] Lecture des bâtiments ({gpkg})...')
    b = gpd.read_file(gpkg, layer='Buildings')
    if b.crs is not None and b.crs.to_epsg() != 31370:
        b = b.to_crs(31370)
    bid_col = find_col(b, 'INSPIRE_ID', 'INSPIREID', 'ID')
    if bid_col is None:
        print(f'[ERREUR] Colonne identifiant introuvable dans Buildings : {list(b.columns)}')
        sys.exit(1)

    bgeoms, braw, key_to_idx, ambiguous = [], [], {}, set()
    for raw_id, geom in zip(b[bid_col].tolist(), b.geometry.tolist()):
        if geom is None or is_blank(raw_id):
            continue
        g = polygonal(shapely.make_valid(geom))
        if g is None or g.area <= 0:
            continue
        idx = len(bgeoms)
        bgeoms.append(g)
        braw.append(raw_id)
        for k in id_keys(raw_id):
            if k in key_to_idx and key_to_idx[k] != idx:
                ambiguous.add(k)
            else:
                key_to_idx[k] = idx
    for k in ambiguous:
        key_to_idx.pop(k, None)
    bids = []
    for raw_id in braw:
        keys = id_keys(raw_id)
        bids.append(next((k for k in keys[1:] if k not in ambiguous and not k.startswith('#')), keys[0]))
    print(f'[URBIS] {len(bgeoms)} bâtiments chargés')

    print('[URBIS] Lecture des adresses...')
    a = gpd.read_file(gpkg, layer='Addresses')
    if a.crs is not None and a.crs.to_epsg() != 31370:
        a = a.to_crs(31370)
    parent_col = find_col(a, 'PARENTID', 'PARENT_ID')
    if parent_col:
        a = a[a[parent_col].apply(is_blank)]
    fre_col = find_col(a, 'STRNAMEFRE', 'STRNAME_FRE')
    dut_col = find_col(a, 'STRNAMEDUT', 'STRNAME_DUT')
    num_col = find_col(a, 'POLICENUM', 'POLICE_NUM', 'HOUSENUMBER')
    bld_col = find_col(a, 'BUILDINGID', 'BUILDING_ID', 'BUILDINGIDENTIFIER', 'BU_ID')
    if not num_col or not bld_col or not (fre_col or dut_col):
        print(f'[ERREUR] Colonnes attendues introuvables dans Addresses : {list(a.columns)}')
        sys.exit(1)

    n = len(a)
    fres = a[fre_col].tolist() if fre_col else [None] * n
    duts = a[dut_col].tolist() if dut_col else [None] * n
    nums = a[num_col].tolist()
    blds = a[bld_col].tolist()

    index = defaultdict(dict)
    bldg_addrs = defaultdict(set)
    linked, unlinked, unresolved = 0, 0, []
    for fre, dut, num, bld in zip(fres, duts, nums, blds):
        if is_blank(num):
            continue
        nbr = norm_nbr(num)
        if not nbr:
            continue
        if is_blank(bld):
            unlinked += 1
            continue
        bidx = next((key_to_idx[k] for k in id_keys(bld) if k in key_to_idx), None)
        if bidx is None:
            unlinked += 1
            if len(unresolved) < 5:
                unresolved.append(str(bld))
            continue
        linked += 1
        display_street = str(fre if not is_blank(fre) else dut).strip()
        label = f'{display_street} {str(num).strip()}'
        variants = set()
        for s in (fre, dut):
            if not is_blank(s):
                variants.update(split_bilingual(s))
        for v in variants:
            index[(v, nbr)][bidx] = label
        bldg_addrs[bidx].add(str(num).strip())

    print(f'[URBIS] {linked} adresses liées à un bâtiment, {unlinked} sans bâtiment résolu')
    if unresolved:
        print(f'[URBIS] Exemples d\'identifiants bâtiment non résolus : {unresolved}')
    if linked == 0:
        print('[ERREUR] Aucune adresse UrbIS liée à un bâtiment : vérifier le format des identifiants.')
        sys.exit(1)
    return bgeoms, bids, key_to_idx, index, bldg_addrs


class OsmHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.wkb = WKBFactory()
        self.objects = []
        self.street_groups = []

    def _variants(self, tags):
        variants = set()
        for t in STREET_NAME_TAGS:
            v = tags.get(t)
            if v:
                variants.update(split_bilingual(v))
        if len(variants) > 1:
            self.street_groups.append(variants)

    def _addr(self, tags):
        hn = tags.get('addr:housenumber')
        if not hn:
            return None
        streets = [tags.get(k) for k in ('addr:street', 'addr:street_official', 'addr:place')]
        streets = [s for s in streets if s]
        if not streets:
            return None
        return {
            'hn': hn,
            'streets': streets,
            'is_building': bool(tags.get('building') or tags.get('building:part')),
            'ref': tags.get('ref:databrussels'),
        }

    def node(self, n):
        info = self._addr(n.tags)
        if info and n.location.valid():
            self.objects.append(('node', n.id, info, Point(n.location.lon, n.location.lat)))

    def way(self, w):
        if w.tags.get('highway'):
            self._variants(w.tags)
        info = self._addr(w.tags)
        if not info:
            return
        coords = [(nd.location.lon, nd.location.lat) for nd in w.nodes if nd.location.valid()]
        if len(coords) < 2:
            return
        geom = None
        if len(coords) >= 4 and coords[0] == coords[-1]:
            try:
                geom = polygonal(shapely.make_valid(Polygon(coords)))
            except Exception:
                geom = None
        if geom is None:
            geom = LineString(coords).centroid
        self.objects.append(('way', w.id, info, geom))

    def relation(self, r):
        if r.tags.get('type') == 'associatedStreet':
            self._variants(r.tags)

    def area(self, a):
        if a.from_way():
            return
        info = self._addr(a.tags)
        if not info:
            return
        try:
            geom = wkb.loads(self.wkb.create_multipolygon(a), hex=True)
        except Exception:
            return
        geom = polygonal(shapely.make_valid(geom))
        if geom is not None:
            self.objects.append(('relation', a.orig_id(), info, geom))


def load_osm(pbf):
    print(f'[OSM] Lecture de {pbf}...')
    h = OsmHandler()
    h.apply_file(pbf, locations=True)
    alias = defaultdict(set)
    for group in h.street_groups:
        for name in group:
            alias[name].update(group - {name})
    print(f'[OSM] {len(h.objects)} objets adresse, {len(alias)} noms de rue avec variantes')
    return h.objects, alias


def ref_index(ref, key_to_idx):
    if not ref:
        return None
    for k in id_keys(ref):
        if k in key_to_idx:
            return key_to_idx[k]
    return None


def classify(g, info, expected, bgeoms, bids, key_to_idx, tree, args):
    exp_idx = set(expected)
    E = bgeoms[next(iter(exp_idx))] if len(exp_idx) == 1 else unary_union([bgeoms[i] for i in exp_idx])
    d = g.distance(E)
    ref_idx = ref_index(info['ref'], key_to_idx)

    if g.geom_type in ('Polygon', 'MultiPolygon') and g.area > 0:
        if ref_idx is not None and ref_idx in exp_idx:
            return None
        ga = g.area
        inter = g.intersection(E).area if d == 0 else 0.0
        own = inter / ga
        if own >= args.overlap_ok or inter / E.area >= args.overlap_ok:
            return None
        if not info['is_building']:
            if d <= args.far:
                return None
            return {'category': 'eloigne', 'host': None, 'distance': d, 'overlap': own}
        best, best_score = None, 0.0
        for j in tree.query(g, predicate='intersects'):
            j = int(j)
            if j in exp_idx:
                continue
            ia = g.intersection(bgeoms[j]).area
            score = max(ia / ga, ia / bgeoms[j].area)
            if score > best_score:
                best, best_score = j, score
        if best is not None and best_score >= args.overlap_ok:
            return {'category': 'mauvais_batiment', 'host': best, 'distance': d,
                    'overlap': own, 'host_overlap': best_score}
        if d > args.far:
            return {'category': 'eloigne', 'host': best, 'distance': d, 'overlap': own}
        return {'category': 'ambigu', 'host': best, 'distance': d, 'overlap': own,
                'host_overlap': best_score}

    p = g if g.geom_type == 'Point' else g.centroid
    d = p.distance(E)
    if d <= args.point_tol:
        return None
    hosts = [int(j) for j in tree.query(p, predicate='intersects') if int(j) not in exp_idx]
    if hosts:
        host = min(hosts, key=lambda j: bgeoms[j].area)
        return {'category': 'mauvais_batiment', 'host': host, 'distance': d}
    if d > args.far:
        return {'category': 'eloigne', 'host': None, 'distance': d}
    return None


def analyse(objects, alias, region, bgeoms, bids, key_to_idx, index, args):
    if region is not None:
        region_prep = prep(region)
        objects = [o for o in objects if region_prep.covers(o[3].representative_point())]
        print(f'[REGION] {len(objects)} objets adresse dans la Région')

    print('[ANALYSE] Projection Lambert 72...')
    geoms = transform_array([o[3] for o in objects], TO_L72)
    tree = STRtree(bgeoms)

    stats = defaultdict(int)
    issues = []
    for i, ((otype, oid, info, g4326), g) in enumerate(zip(objects, geoms)):
        if i and i % 20000 == 0:
            print(f'[ANALYSE]   {i}/{len(objects)}')
        variants = set()
        for s in info['streets']:
            for p in split_bilingual(s):
                variants.add(p)
                variants.update(alias.get(p, ()))
        for raw_hn in [h.strip() for h in info['hn'].split(';') if h.strip()]:
            nbr = norm_nbr(raw_hn)
            stats['adresses_osm'] += 1
            candidates = {}
            for v in variants:
                candidates.update(index.get((v, nbr), {}))
            if not candidates:
                stats['sans_equivalent_urbis_lie'] += 1
                continue
            near = {b: lbl for b, lbl in candidates.items()
                    if g.distance(bgeoms[b]) <= args.search_radius}
            if not near:
                stats['homonyme_lointain'] += 1
                continue
            res = classify(g, info, near, bgeoms, bids, key_to_idx, tree, args)
            if res is None:
                stats['ok'] += 1
                continue
            stats[res['category']] += 1
            res.update({
                'otype': otype,
                'oid': oid,
                'street': info['streets'][0],
                'hn': raw_hn,
                'geom_wgs': g4326,
                'expected': sorted(near),
            })
            issues.append(res)
    print(f'[ANALYSE] {dict(stats)}')
    return issues, stats


def enrich(issues, bgeoms, bids, bldg_addrs):
    wgs_cache = {}

    def bw(i):
        if i not in wgs_cache:
            wgs_cache[i] = to_wgs(bgeoms[i])
        return wgs_cache[i]

    for it in issues:
        it['expected_ids'] = [bids[i] for i in it['expected']]
        it['expected_wgs'] = [bw(i) for i in it['expected']]
        it['host_id'] = bids[it['host']] if it.get('host') is not None else None
        it['host_wgs'] = bw(it['host']) if it.get('host') is not None else None
        it['host_addrs'] = (sorted(bldg_addrs.get(it['host'], ()), key=nat_key)
                            if it.get('host') is not None else [])
        it['osm_url'] = f'https://www.openstreetmap.org/{it["otype"]}/{it["oid"]}'
    return issues


def write_txt(issues, stats, path, urbis_date, args):
    by_cat = defaultdict(list)
    for it in issues:
        by_cat[it['category']].append(it)

    L = ['=' * 78,
         'RAPPORT : ADRESSES OSM PLACÉES SUR UN AUTRE BÂTIMENT QUE DANS URBIS',
         'Région de Bruxelles-Capitale — UrbIS Parcelles & Bâtiments vs OpenStreetMap',
         '=' * 78,
         f'Date du rapport       : {date.today().isoformat()}',
         f'Source UrbIS (GPKG)   : publication {urbis_date}',
         '',
         'PARAMÈTRES DE TOLÉRANCE',
         '-' * 40,
         f'  Recouvrement minimal pour considérer un bâtiment identique : {args.overlap_ok:.0%}',
         f'  Tolérance point / bâtiment                                 : {args.point_tol} m',
         f'  Distance au-delà de laquelle une adresse est « éloignée »  : {args.far} m',
         f'  Rayon de recherche de l\'adresse UrbIS homologue           : {args.search_radius} m',
         '',
         'RÉSUMÉ',
         '-' * 40,
         f'  Adresses OSM analysées                      : {stats["adresses_osm"]:>7}',
         f'  Sans équivalent UrbIS lié à un bâtiment     : {stats["sans_equivalent_urbis_lie"]:>7}',
         f'  Homonyme UrbIS trop éloigné (ignoré)        : {stats["homonyme_lointain"]:>7}',
         f'  OK (bon bâtiment, dans la tolérance)        : {stats["ok"]:>7}',
         f'  Sur un autre bâtiment                       : {stats["mauvais_batiment"]:>7}',
         f'  Hors bâtiment et éloignée                   : {stats["eloigne"]:>7}',
         f'  Chevauchement ambigu                        : {stats["ambigu"]:>7}',
         '']

    for cat in ('mauvais_batiment', 'eloigne', 'ambigu'):
        items = by_cat.get(cat, [])
        L += ['=' * 78, f'{CATEGORY_LABELS[cat]} ({len(items)})', '=' * 78, '']
        if not items:
            L += ['  (aucune)', '']
            continue
        groups = defaultdict(list)
        for it in items:
            groups[normalize(it['street'])].append(it)
        for key in sorted(groups):
            g = sorted(groups[key], key=lambda x: nat_key(x['hn']))
            L.append('-' * 78)
            L.append(f'{g[0]["street"]}  ({len(g)})')
            for it in g:
                L.append(f'  n°{it["hn"]:<8} {it["otype"]}/{it["oid"]}')
                if it.get('host_id'):
                    on_host = ', '.join(it['host_addrs']) if it['host_addrs'] else '(aucune adresse)'
                    L.append(f'      → UrbIS y place : {on_host}')
                L.append(f'      {it["osm_url"]}')
            L.append('')

    L += ['=' * 78, 'FIN DU RAPPORT', '=' * 78]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f'[OK] Rapport écrit : {path}')


def write_csv(issues, path):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['categorie', 'rue', 'numero', 'osm_type', 'osm_id',
                    'urbis_y_place', 'osm_url'])
        for it in sorted(issues, key=lambda x: (x['category'], normalize(x['street']), nat_key(x['hn']))):
            w.writerow([it['category'], it['street'], it['hn'], it['otype'], it['oid'],
                        ';'.join(it['host_addrs']), it['osm_url']])
    print(f'[OK] CSV écrit : {path}')


def write_geojson(issues, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    feats = []
    for it in issues:
        base = {'categorie': it['category'], 'rue': it['street'], 'numero': it['hn'],
                'osm': f'{it["otype"]}/{it["oid"]}', 'osm_url': it['osm_url'],
                'distance_m': round(it['distance'], 1)}
        feats.append({'type': 'Feature', 'geometry': mapping(it['geom_wgs']),
                      'properties': {**base, 'role': 'osm'}})
        for bid, bg in zip(it['expected_ids'], it['expected_wgs']):
            feats.append({'type': 'Feature', 'geometry': mapping(bg),
                          'properties': {**base, 'role': 'urbis_attendu', 'batiment': bid}})
        if it.get('host_wgs') is not None:
            feats.append({'type': 'Feature', 'geometry': mapping(it['host_wgs']),
                          'properties': {**base, 'role': 'urbis_occupe', 'batiment': it['host_id'],
                                         'adresses_urbis': ';'.join(it['host_addrs'])}})
        target = unary_union(it['expected_wgs']).representative_point()
        src = it['geom_wgs'].representative_point()
        feats.append({'type': 'Feature', 'geometry': mapping(LineString([src, target])),
                      'properties': {**base, 'role': 'deplacement'}})
    path = os.path.join(out_dir, 'wrong_building_issues.geojson')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': feats}, f, ensure_ascii=False)
    print(f'[OK] GeoJSON écrit : {path} ({len(feats)} features)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pbf', default='brussels_capital_region-latest.osm.pbf')
    ap.add_argument('--gpkg', default=None)
    ap.add_argument('--overlap-ok', type=float, default=float(os.environ.get('WB_OVERLAP_OK', 0.5)))
    ap.add_argument('--point-tol', type=float, default=float(os.environ.get('WB_POINT_TOL', 2.0)))
    ap.add_argument('--far', type=float, default=float(os.environ.get('WB_FAR', 25.0)))
    ap.add_argument('--search-radius', type=float, default=float(os.environ.get('WB_SEARCH_RADIUS', 300.0)))
    ap.add_argument('--no-region', action='store_true')
    args = ap.parse_args()

    print(f'[START] {datetime.now().isoformat(timespec="seconds")}')
    if not args.gpkg:
        found = sorted({f for f in glob.glob('*04000*.gpkg') if not os.path.basename(f).startswith('BeSt')}, reverse=True)
        args.gpkg = found[0] if found else None
    pbf, gpkg, urbis_date = ensure_inputs(args)

    bgeoms, bids, key_to_idx, index, bldg_addrs = load_urbis(gpkg)
    objects, alias = load_osm(pbf)
    region = None if args.no_region else load_region()

    issues, stats = analyse(objects, alias, region, bgeoms, bids, key_to_idx, index, args)
    issues = enrich(issues, bgeoms, bids, bldg_addrs)

    today = date.today().isoformat()
    write_txt(issues, stats, f'wrong_building_report_{today}.txt', urbis_date, args)
    write_csv(issues, f'wrong_building_report_{today}.csv')
    write_geojson(issues, GEOJSON_DIR)


if __name__ == '__main__':
    main()
