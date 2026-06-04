#!/usr/bin/env python3
"""
compare-postal-codes.py

Pour chaque adresse OSM dans la région bruxelloise :
  1. Si addr:postcode est présent → loggé en anomalie, puis ignoré (on force le spatial)
  2. Code postal calculé spatialement (point-in-polygon dans les relations boundary=postal_code)
  3. Match avec le ZIPCODE de l'adresse correspondante dans UrbIS (rue + numéro)
  4. Si mismatch → inclus dans le rapport "CP à vérifier"

Sortie : rapport texte postal_code_report_YYYY-MM-DD.txt
"""

import sys
import os
import glob
import json
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import unicodedata
import re
from datetime import datetime, date
from collections import defaultdict

import osmium
import geopandas as gpd
from shapely.geometry import Point, shape, MultiPolygon, Polygon
from shapely.prepared import prep
from shapely.ops import unary_union

##FEED_URL     = 'https://urbisdownload.datastore.brussels/atomfeed/2cf42541-1813-11ef-8a81-00090ffe0001-en.xml'
FEED_URL     = 'https://urbisdownload.datastore.brussels/atomfeed/a8c9ccde-5c2b-11ed-913a-900f0cda5d5c-en.xml'
OSM_PBF_URL  = 'https://raw.githubusercontent.com/PasLoin/Osm-python-analyse_Belgium/main/pbf_analyse/history/Brussels-daily.pbf'
OSM_PBF_FILE = 'brussels_capital_region-latest.osm.pbf'
ATOM_NS      = 'http://www.w3.org/2005/Atom'
HEADERS      = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize(s):
    if not s:
        return ''
    s = s.strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = ' '.join(s.split())
    return s

def split_bilingual(s):
    s = normalize(s)
    return [p for p in re.split(r' [-\u2013\u2014] ', s) if p]


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def find_latest_gpkg(feed_url):
    print('[FEED] Lecture du feed ATOM...')
    req = urllib.request.Request(feed_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        xml_data = r.read()
    root = ET.fromstring(xml_data)
    candidates = []
    for link in root.iter(f'{{{ATOM_NS}}}link'):
        href = link.get('href', '')
        time = link.get('time', '')
        if 'GPKG' in href and '_04000_' in href and href.endswith('.zip'):
            try:
                dt = datetime.fromisoformat(time.replace('Z', '+00:00'))
                candidates.append((dt, href))
            except ValueError:
                pass
    if not candidates:
        print('[ERREUR] Aucun fichier GPKG 04000 trouvé dans le feed.')
        sys.exit(1)
    candidates.sort(reverse=True)
    latest_dt, latest_url = candidates[0]
    print(f'[FEED] Dernière version : {latest_dt.date()} → {latest_url}')
    return latest_dt, latest_url


def download(url, dest):
    print(f'[DL] Téléchargement de {os.path.basename(url)}...')
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get('Content-Length', 0))
        downloaded = 0
        with open(dest, 'wb') as f:
            while chunk := r.read(65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = min(downloaded * 100 // total, 100)
                    print(f'\r    {pct}%', end='', flush=True)
    print()
    print(f'[DL] Sauvegardé : {dest}')


def extract_gpkg(zip_path):
    print(f'[ZIP] Extraction de {zip_path}...')
    with zipfile.ZipFile(zip_path, 'r') as z:
        gpkg_files = [f for f in z.namelist() if f.endswith('.gpkg')]
        if not gpkg_files:
            print('[ERREUR] Aucun fichier .gpkg dans le ZIP.')
            sys.exit(1)
        gpkg_name = gpkg_files[0]
        out_path = os.path.abspath(gpkg_name)
        if not out_path.startswith(os.path.abspath('.') + os.sep):
            print('[ERREUR] Nom de fichier .gpkg invalide.')
            sys.exit(1)
        z.extract(gpkg_name, '.')
        print(f'[ZIP] Extrait : {gpkg_name}')
        return gpkg_name


# ---------------------------------------------------------------------------
# OSM pass 1 : collecter les géométries des relations boundary=postal_code
# ---------------------------------------------------------------------------

class PostalCodeWayCollector(osmium.SimpleHandler):
    """Collecte les coords de tous les ways pour reconstruire les polygones."""
    def __init__(self):
        super().__init__()
        self.ways = {}  # way_id → list of (lon, lat)

    def way(self, w):
        coords = []
        for n in w.nodes:
            if n.location.valid():
                coords.append((n.location.lon, n.location.lat))
        if coords:
            self.ways[w.id] = coords


class PostalCodeRelationCollector(osmium.SimpleHandler):
    """Collecte les relations boundary=postal_code et leurs members (way ids)."""
    def __init__(self):
        super().__init__()
        # postal_code → list of way_ids
        self.relations = {}
        self.relation_ids = {}  # postal_code → osm relation id

    def relation(self, r):
        tags = r.tags
        if tags.get('type') != 'boundary':
            return
        if tags.get('boundary') != 'postal_code':
            return
        pc = (tags.get('postal_code') or tags.get('ref') or '').strip()
        if not (pc.isdigit() and len(pc) == 4):
            return
        way_ids = [m.ref for m in r.members if m.type == 'w']
        self.relations[pc] = way_ids
        self.relation_ids[pc] = r.id


def build_postal_polygons(pbf_path):
    """
    Reconstruit les polygones des relations boundary=postal_code
    depuis le PBF. Retourne dict: postal_code → shapely geometry (prepared).
    """
    print('[PC] Collecte des relations boundary=postal_code...')
    rel_collector = PostalCodeRelationCollector()
    rel_collector.apply_file(pbf_path)
    print(f'[PC] {len(rel_collector.relations)} relations trouvées')

    if not rel_collector.relations:
        return {}, {}

    # Collecter les ways nécessaires
    needed_ways = set()
    for way_ids in rel_collector.relations.values():
        needed_ways.update(way_ids)

    print(f'[PC] Collecte de {len(needed_ways)} ways...')
    way_collector = PostalCodeWayCollector()
    way_collector.apply_file(pbf_path, locations=True)

    # Construire les polygones
    postal_polygons = {}
    postal_relation_ids = rel_collector.relation_ids

    for pc, way_ids in rel_collector.relations.items():
        rings = []
        for wid in way_ids:
            coords = way_collector.ways.get(wid, [])
            if len(coords) >= 3:
                # Fermer l'anneau si nécessaire
                if coords[0] != coords[-1]:
                    coords = coords + [coords[0]]
                rings.append(coords)
        if not rings:
            continue
        try:
            polys = [Polygon(r) for r in rings if len(r) >= 4]
            if not polys:
                continue
            geom = unary_union(polys)
            postal_polygons[pc] = geom
        except Exception as e:
            print(f'[WARN] Impossible de construire le polygone pour {pc}: {e}')

    print(f'[PC] {len(postal_polygons)} polygones construits')
    return postal_polygons, postal_relation_ids


def find_postal_code(lon, lat, postal_polygons, prepared_cache):
    """Retourne le code postal OSM pour un point donné (None si hors zone)."""
    pt = Point(lon, lat)
    for pc, geom in postal_polygons.items():
        if pc not in prepared_cache:
            prepared_cache[pc] = prep(geom)
        if prepared_cache[pc].contains(pt):
            return pc
    return None


# ---------------------------------------------------------------------------
# OSM pass 2 : collecter les adresses
# ---------------------------------------------------------------------------

class AddressCollector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.addresses = []   # list of dicts
        self.with_postcode = []  # anomalies : addr:postcode présent

    def _process(self, osm_type, osm_id, tags, lat, lon):
        housenumber = tags.get('addr:housenumber')
        street = tags.get('addr:street') or tags.get('addr:street_official')
        if not housenumber or not street:
            return
        if lat is None or lon is None:
            return

        postcode_tag = tags.get('addr:postcode', '').strip()
        entry = {
            'osm_type':    osm_type,
            'osm_id':      osm_id,
            'street':      street,
            'housenumber': housenumber,
            'lat':         lat,
            'lon':         lon,
            'postcode_tag': postcode_tag if postcode_tag else None,
        }
        if postcode_tag:
            self.with_postcode.append(entry)
        self.addresses.append(entry)

    def node(self, n):
        if not n.location.valid():
            return
        self._process('node', n.id, n.tags, n.location.lat, n.location.lon)

    def way(self, w):
        if not w.tags.get('addr:housenumber'):
            return
        try:
            lats, lons = [], []
            for nd in w.nodes:
                if nd.location.valid():
                    lats.append(nd.location.lat)
                    lons.append(nd.location.lon)
            if lats:
                lat = sum(lats) / len(lats)
                lon = sum(lons) / len(lons)
                self._process('way', w.id, w.tags, lat, lon)
        except Exception:
            pass


def load_osm_addresses(pbf_path):
    print(f'[OSM] Collecte des adresses OSM...')
    handler = AddressCollector()
    handler.apply_file(pbf_path, locations=True)
    print(f'[OSM] {len(handler.addresses)} adresses collectées')
    print(f'[OSM] {len(handler.with_postcode)} adresses avec addr:postcode (anomalie)')
    return handler.addresses, handler.with_postcode


# ---------------------------------------------------------------------------
# UrbIS : index rue+numéro → ZIPCODE
# ---------------------------------------------------------------------------

def load_urbis_index(gpkg_path):
    print(f'[URBIS] Lecture de {gpkg_path}...')
    gdf = gpd.read_file(gpkg_path, layer='Addresses')
    gdf = gdf[gdf['PARENTID'].isna()].copy()

    index = {}  # (norm_street, norm_nbr) → zipcode (str)
    for _, row in gdf.iterrows():
        nbr = str(row['POLICENUM']).strip() if row['POLICENUM'] else ''
        if not nbr:
            continue
        zc = str(row['ZIPCODE']).strip() if row['ZIPCODE'] else ''
        if zc.endswith('.0'):
            zc = zc[:-2]
        if not (zc.isdigit() and len(zc) == 4):
            continue
        for col in ('STRNAMEFRE', 'STRNAMEDUT'):
            val = row.get(col)
            if not val:
                continue
            for part in split_bilingual(val):
                key = (part, normalize(nbr))
                if key not in index:
                    index[key] = zc

    print(f'[URBIS] {len(index)} entrées dans l\'index rue+numéro')
    return index


def lookup_urbis_zipcode(street, housenumber, urbis_index):
    """Retourne le ZIPCODE UrbIS pour une adresse OSM, ou None."""
    norm_street = normalize(street)
    norm_nbr    = normalize(housenumber)
    # Essai direct
    zc = urbis_index.get((norm_street, norm_nbr))
    if zc:
        return zc
    # Essai avec les variantes bilingues de la rue OSM
    for part in split_bilingual(street):
        zc = urbis_index.get((part, norm_nbr))
        if zc:
            return zc
    return None


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def build_report(
    anomalies_postcode_tag,
    mismatches,
    no_postal_zone,
    not_in_urbis,
    stats,
    urbis_date,
):
    today = date.today().isoformat()
    L = []

    L.append('=' * 72)
    L.append('RAPPORT DE COMPARAISON DES CODES POSTAUX PAR ADRESSE')
    L.append('Région de Bruxelles-Capitale — UrbIS vs OpenStreetMap')
    L.append('=' * 72)
    L.append(f'Date du rapport     : {today}')
    L.append(f'Source UrbIS        : publication {urbis_date}')
    L.append(f'Source OSM (PBF)    : {OSM_PBF_URL}')
    L.append('')

    L.append('RÉSUMÉ')
    L.append('-' * 40)
    L.append(f'  Adresses OSM analysées             : {stats["total"]:>6}')
    L.append(f'  Avec addr:postcode (anomalie)       : {stats["with_postcode_tag"]:>6}')
    L.append(f'  Hors zone postal_code OSM           : {stats["no_postal_zone"]:>6}')
    L.append(f'  Adresse absente d\'UrbIS             : {stats["not_in_urbis"]:>6}')
    L.append(f'  CP OSM ≠ CP UrbIS (à vérifier)     : {stats["mismatches"]:>6}')
    L.append(f'  CP OSM = CP UrbIS (OK)              : {stats["ok"]:>6}')
    L.append('')

    # -----------------------------------------------------------------------
    L.append('ANOMALIE : ADRESSES AVEC addr:postcode DIRECT')
    L.append('(le tag addr:postcode ne devrait pas être utilisé à Bruxelles,')
    L.append(' le code postal est porté par la relation boundary=postal_code)')
    L.append('-' * 40)
    if anomalies_postcode_tag:
        L.append(f'  {"OSM ref":<20} {"Rue":<35} {"Numéro":<10} {"addr:postcode"}')
        L.append(f'  {"-"*18:<20} {"-"*33:<35} {"-"*8:<10} {"-"*12}')
        for a in sorted(anomalies_postcode_tag, key=lambda x: x['street']):
            ref = f'{a["osm_type"]}/{a["osm_id"]}'
            L.append(f'  {ref:<20} {a["street"][:33]:<35} {a["housenumber"]:<10} {a["postcode_tag"]}')
    else:
        L.append('  (aucune)')
    L.append('')

    # -----------------------------------------------------------------------
    L.append('CP À VÉRIFIER : CP CALCULÉ OSM ≠ CP URBIS')
    L.append('-' * 40)
    if mismatches:
        L.append(f'  {"OSM ref":<20} {"Rue":<35} {"Numéro":<10} {"CP OSM":<8} {"CP UrbIS"}')
        L.append(f'  {"-"*18:<20} {"-"*33:<35} {"-"*8:<10} {"-"*6:<8} {"-"*8}')
        for m in sorted(mismatches, key=lambda x: (x['cp_osm'], x['street'])):
            ref = f'{m["osm_type"]}/{m["osm_id"]}'
            L.append(
                f'  {ref:<20} {m["street"][:33]:<35} {m["housenumber"]:<10} '
                f'{m["cp_osm"]:<8} {m["cp_urbis"]}'
            )
    else:
        L.append('  (aucun mismatch — tout est cohérent !)')
    L.append('')

    # -----------------------------------------------------------------------
    L.append('ADRESSES OSM HORS ZONE boundary=postal_code')
    L.append('(adresses dans le PBF mais pas dans une relation postal_code OSM)')
    L.append('-' * 40)
    if no_postal_zone:
        L.append(f'  {"OSM ref":<20} {"Rue":<35} {"Numéro":<10} {"CP UrbIS"}')
        L.append(f'  {"-"*18:<20} {"-"*33:<35} {"-"*8:<10} {"-"*8}')
        for a in sorted(no_postal_zone, key=lambda x: x['street']):
            ref = f'{a["osm_type"]}/{a["osm_id"]}'
            cp_u = a.get('cp_urbis', '?')
            L.append(f'  {ref:<20} {a["street"][:33]:<35} {a["housenumber"]:<10} {cp_u}')
    else:
        L.append('  (aucune)')
    L.append('')

    # -----------------------------------------------------------------------
    L.append('ADRESSES OSM SANS CORRESPONDANCE DANS URBIS')
    L.append('(rue+numéro introuvable dans le GPKG UrbIS)')
    L.append('-' * 40)
    if not_in_urbis:
        L.append(f'  {"OSM ref":<20} {"Rue":<35} {"Numéro":<10} {"CP OSM calculé"}')
        L.append(f'  {"-"*18:<20} {"-"*33:<35} {"-"*8:<10} {"-"*14}')
        for a in sorted(not_in_urbis, key=lambda x: x['street']):
            ref = f'{a["osm_type"]}/{a["osm_id"]}'
            cp_o = a.get('cp_osm', '?')
            L.append(f'  {ref:<20} {a["street"][:33]:<35} {a["housenumber"]:<10} {cp_o}')
    else:
        L.append('  (aucune)')
    L.append('')

    L.append('=' * 72)
    L.append('FIN DU RAPPORT')
    L.append('=' * 72)
    return '\n'.join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # 1. GPKG UrbIS
    existing_gpkg = glob.glob('*.gpkg') + glob.glob('**/*.gpkg')
    urbis_date = 'inconnue'

    if existing_gpkg:
        gpkg_path = existing_gpkg[0]
        print(f'[INFO] GPKG déjà présent : {gpkg_path}')
        if os.path.isfile('version.json'):
            with open('version.json') as f:
                urbis_date = json.load(f).get('urbis_date', 'inconnue')
    else:
        latest_dt, latest_url = find_latest_gpkg(FEED_URL)
        urbis_date = str(latest_dt.date())
        zip_name = os.path.basename(latest_url)
        if not os.path.isfile(zip_name):
            download(latest_url, zip_name)
        gpkg_path = extract_gpkg(zip_name)

    # 2. PBF OSM
    if not os.path.isfile(OSM_PBF_FILE):
        download(OSM_PBF_URL, OSM_PBF_FILE)
    else:
        print(f'[INFO] PBF déjà présent : {OSM_PBF_FILE}')

    # 3. Construire les polygones postal_code depuis OSM
    postal_polygons, postal_relation_ids = build_postal_polygons(OSM_PBF_FILE)

    # 4. Charger les adresses OSM
    osm_addresses, anomalies_postcode_tag = load_osm_addresses(OSM_PBF_FILE)

    # 5. Charger l'index UrbIS
    urbis_index = load_urbis_index(gpkg_path)

    # 6. Analyse adresse par adresse
    print('[ANALYSE] Calcul spatial et comparaison CP...')
    prepared_cache = {}
    mismatches   = []
    no_postal_zone = []
    not_in_urbis = []
    ok_count     = 0

    for i, addr in enumerate(osm_addresses):
        if i % 10000 == 0:
            print(f'\r    {i}/{len(osm_addresses)}', end='', flush=True)

        lon, lat = addr['lon'], addr['lat']

        # Code postal calculé spatialement (on ignore addr:postcode)
        cp_osm = find_postal_code(lon, lat, postal_polygons, prepared_cache)

        # Code postal UrbIS
        cp_urbis = lookup_urbis_zipcode(addr['street'], addr['housenumber'], urbis_index)

        addr['cp_osm']   = cp_osm
        addr['cp_urbis'] = cp_urbis

        if cp_osm is None:
            no_postal_zone.append(addr)
            continue

        if cp_urbis is None:
            not_in_urbis.append(addr)
            continue

        if cp_osm != cp_urbis:
            mismatches.append(addr)
        else:
            ok_count += 1

    print(f'\r    {len(osm_addresses)}/{len(osm_addresses)}')
    print('[ANALYSE] Terminé.')

    stats = {
        'total':            len(osm_addresses),
        'with_postcode_tag': len(anomalies_postcode_tag),
        'no_postal_zone':   len(no_postal_zone),
        'not_in_urbis':     len(not_in_urbis),
        'mismatches':       len(mismatches),
        'ok':               ok_count,
    }

    # 7. Rapport
    report = build_report(
        anomalies_postcode_tag=anomalies_postcode_tag,
        mismatches=mismatches,
        no_postal_zone=no_postal_zone,
        not_in_urbis=not_in_urbis,
        stats=stats,
        urbis_date=urbis_date,
    )

    output_file = f'postal_code_report_{date.today().isoformat()}.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\n[OK] Rapport écrit : {output_file}')
