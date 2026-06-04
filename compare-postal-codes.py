#!/usr/bin/env python3
"""
compare-postal-codes.py

Pour chaque adresse OSM dans la région bruxelloise :
  1. Si addr:postcode est présent → loggé en anomalie, le code postal
     est quand même calculé spatialement (on ignore addr:postcode)
  2. Code postal calculé spatialement (point-in-polygon dans les relations
     boundary=postal_code OSM)
  3. Match avec le code postal BeSt (haspostalinfo_objectidentifier) via
     join sur le nom de rue normalisé + numéro
  4. Si mismatch → inclus dans le rapport "CP à vérifier"

Source BeSt : GPKG sectionID=04000, URL directe (pas de feed — bloqué sur GitHub Actions)
  Pattern : .../BeSt/FullDownload/GPKG/BeStBrussels_31370_GPKG_04000_YYYYMMDD.zip
  Le script essaie les 30 derniers jours jusqu'à trouver un fichier disponible.

Source OSM : PBF Brussels daily
Sortie    : postal_code_report_YYYY-MM-DD.txt
"""

import sys
import os
import glob
import json
import urllib.request
import urllib.error
import zipfile
import unicodedata
import re
from datetime import datetime, date, timedelta
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep
import geopandas as gpd
import osmium

GPKG_BASE_URL = 'https://urbisdownload.datastore.brussels/BeSt/FullDownload/GPKG/BeStBrussels_31370_GPKG_04000_{date}.zip'
OSM_PBF_URL   = 'https://raw.githubusercontent.com/PasLoin/Osm-python-analyse_Belgium/main/pbf_analyse/history/Brussels-daily.pbf'
OSM_PBF_FILE  = 'brussels_capital_region-latest.osm.pbf'
HEADERS       = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}


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

def find_latest_best_gpkg_url(max_days=60):
    """
    Cherche le GPKG 04000 le plus récent en testant les dates des 60 derniers jours.
    Contourne le timeout sur le feed ATOM depuis GitHub Actions.
    """
    print('[BeSt] Recherche du GPKG 04000 le plus récent...')
    today = date.today()
    for delta in range(max_days):
        d = today - timedelta(days=delta)
        date_str = d.strftime('%Y%m%d')
        url = GPKG_BASE_URL.format(date=date_str)
        try:
            req = urllib.request.Request(url, method='HEAD', headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    print(f'[BeSt] Fichier trouvé : {date_str} → {url}')
                    return d, url
        except (urllib.error.HTTPError, urllib.error.URLError, Exception):
            continue
    print('[ERREUR] Aucun GPKG 04000 trouvé dans les 60 derniers jours.')
    sys.exit(1)


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
            print('[ERREUR] Aucun .gpkg dans le ZIP.')
            sys.exit(1)
        gpkg_name = gpkg_files[0]
        out_path = os.path.abspath(gpkg_name)
        if not out_path.startswith(os.path.abspath('.') + os.sep):
            print('[ERREUR] Nom .gpkg invalide.')
            sys.exit(1)
        z.extract(gpkg_name, '.')
        print(f'[ZIP] Extrait : {gpkg_name}')
        return gpkg_name


# ---------------------------------------------------------------------------
# BeSt : index (norm_street, norm_nbr) → postal_code
# ---------------------------------------------------------------------------

def _oid(val):
    """Convertit un objectidentifier Real GPKG (ex: 12340.0) en str entier propre."""
    try:
        return str(int(float(val)))
    except (ValueError, TypeError):
        return str(val).strip()


def load_best_index(gpkg_path):
    print(f'[BeSt] Lecture de {gpkg_path}...')

    streets_gdf = gpd.read_file(gpkg_path, layer='BrusselsStreetname_04000')
    street_map = {}
    for _, row in streets_gdf.iterrows():
        oid = _oid(row['objectidentifier'])
        fr  = str(row.get('spelling_fr') or '').strip()
        nl  = str(row.get('spelling_nl') or '').strip()
        street_map[oid] = (fr, nl)
    print(f'[BeSt] {len(street_map)} rues chargées')

    addr_gdf = gpd.read_file(gpkg_path, layer='BrusselsAddressL72_04000')
    if 'status' in addr_gdf.columns:
        addr_gdf = addr_gdf[addr_gdf['status'].str.lower().str.contains('current', na=False)]

    index = {}
    skipped = 0
    for _, row in addr_gdf.iterrows():
        nbr = str(row.get('housenumber') or '').strip()
        if not nbr:
            skipped += 1
            continue
        pc = str(row.get('haspostalinfo_objectidentifier') or '').strip()
        if not (pc.isdigit() and len(pc) == 4):
            skipped += 1
            continue
        street_oid = _oid(row.get('hasstreetname_objectidentifier'))
        names = street_map.get(street_oid, ('', ''))
        norm_nbr = normalize(nbr)
        for raw_name in names:
            if not raw_name:
                continue
            for variant in split_bilingual(raw_name):
                key = (variant, norm_nbr)
                if key not in index:
                    index[key] = pc

    print(f'[BeSt] {len(index)} entrées dans l\'index rue+numéro ({skipped} ignorées)')
    return index


def lookup_best_zipcode(street, housenumber, best_index):
    norm_nbr = normalize(housenumber)
    for part in ([normalize(street)] + split_bilingual(street)):
        zc = best_index.get((part, norm_nbr))
        if zc:
            return zc
    return None


# ---------------------------------------------------------------------------
# OSM pass 1 : polygones boundary=postal_code
# ---------------------------------------------------------------------------

class PostalCodeHandler(osmium.SimpleHandler):
    """
    Collecte en une seule passe :
    - les relations boundary=postal_code (way members + tags)
    - les coords de tous les ways nécessaires
    """
    def __init__(self):
        super().__init__()
        self.relations   = {}   # pc → list of (way_id, role)
        self.relation_ids = {}  # pc → osm relation id
        self.ways        = {}   # way_id → [(lon, lat), ...]

    def way(self, w):
        coords = []
        for n in w.nodes:
            if n.location.valid():
                coords.append((n.location.lon, n.location.lat))
        if coords:
            self.ways[w.id] = coords

    def relation(self, r):
        tags = r.tags
        if tags.get('type') != 'boundary' or tags.get('boundary') != 'postal_code':
            return
        pc = (tags.get('postal_code') or tags.get('ref') or '').strip()
        if pc.isdigit() and len(pc) == 4:
            self.relations[pc]    = [(m.ref, m.role) for m in r.members if m.type == 'w']
            self.relation_ids[pc] = r.id


def _chain_ways(segments):
    """
    Assemble une liste de segments (listes de coordonnées) en anneaux fermés.
    Retourne une liste d'anneaux (chaque anneau = liste de (lon,lat) fermée).
    """
    # Copie pour pouvoir retirer les segments utilisés
    segs = [list(s) for s in segments if len(s) >= 2]
    rings = []

    while segs:
        # Démarrer un nouvel anneau avec le premier segment disponible
        ring = list(segs.pop(0))
        changed = True
        while changed:
            changed = False
            for i, seg in enumerate(segs):
                if not seg:
                    continue
                # Essayer de connecter seg (ou son inverse) à la fin de l'anneau
                if _close_enough(ring[-1], seg[0]):
                    ring.extend(seg[1:])
                    segs.pop(i)
                    changed = True
                    break
                elif _close_enough(ring[-1], seg[-1]):
                    ring.extend(reversed(seg[:-1]))
                    segs.pop(i)
                    changed = True
                    break
                # Essayer de connecter au début de l'anneau
                elif _close_enough(ring[0], seg[-1]):
                    ring = seg[:-1] + ring
                    segs.pop(i)
                    changed = True
                    break
                elif _close_enough(ring[0], seg[0]):
                    ring = list(reversed(seg[1:])) + ring
                    segs.pop(i)
                    changed = True
                    break
        # Fermer l'anneau si nécessaire
        if len(ring) >= 3 and not _close_enough(ring[0], ring[-1]):
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)

    return rings


def _close_enough(p1, p2, tol=1e-7):
    return abs(p1[0]-p2[0]) < tol and abs(p1[1]-p2[1]) < tol


def build_postal_polygons(pbf_path):
    print('[PC] Collecte des relations boundary=postal_code...')
    handler = PostalCodeHandler()
    handler.apply_file(pbf_path, locations=True)
    print(f'[PC] {len(handler.relations)} relations trouvées')
    if not handler.relations:
        return {}, {}

    postal_polygons = {}
    for pc, way_refs in handler.relations.items():
        # Récupérer les segments dans l'ordre (outer en premier, inner ensuite)
        outer_segs = []
        inner_segs = []
        for wid, role in way_refs:
            coords = handler.ways.get(wid, [])
            if len(coords) < 2:
                continue
            if role == 'inner':
                inner_segs.append(coords)
            else:
                outer_segs.append(coords)

        if not outer_segs:
            continue

        try:
            outer_rings = _chain_ways(outer_segs)
            inner_rings = _chain_ways(inner_segs)

            if not outer_rings:
                continue

            from shapely.geometry import LinearRing
            polys = []
            for oring in outer_rings:
                holes = []
                for iring in inner_rings:
                    try:
                        hole = Polygon(iring)
                        if not hole.is_valid:
                            hole = hole.buffer(0)
                        if not hole.is_empty:
                            holes.append(hole.exterior.coords)
                    except Exception:
                        pass
                try:
                    p = Polygon(oring, holes)
                except Exception:
                    p = Polygon(oring)
                if not p.is_valid:
                    p = p.buffer(0)
                if not p.is_empty:
                    polys.append(p)

            if polys:
                geom = unary_union(polys) if len(polys) > 1 else polys[0]
                if not geom.is_valid:
                    geom = geom.buffer(0)
                postal_polygons[pc] = geom
        except Exception as e:
            print(f'[WARN] Polygone {pc} ignoré : {e}')

    print(f'[PC] {len(postal_polygons)} polygones construits')
    return postal_polygons, handler.relation_ids


def find_postal_code(lon, lat, postal_polygons, prepared_cache):
    pt = Point(lon, lat)
    # Passe 1 : covers (inclut les points sur la frontière)
    for pc, geom in postal_polygons.items():
        if pc not in prepared_cache:
            prepared_cache[pc] = prep(geom)
        if prepared_cache[pc].covers(pt):
            return pc
    # Passe 2 : fallback sur le polygone le plus proche (cas limite de frontière)
    best_pc   = None
    best_dist = float('inf')
    for pc, geom in postal_polygons.items():
        d = geom.distance(pt)
        if d < best_dist:
            best_dist = d
            best_pc   = pc
    # N'utiliser le fallback que si le point est très proche d'une frontière (< 10m en degrés ≈ 0.0001°)
    if best_pc is not None and best_dist < 0.0001:
        return best_pc
    return None


# ---------------------------------------------------------------------------
# OSM pass 2 : adresses
# ---------------------------------------------------------------------------

class AddressCollector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.addresses     = []
        self.with_postcode = []

    def _process(self, osm_type, osm_id, tags, lat, lon):
        housenumber = tags.get('addr:housenumber')
        street      = tags.get('addr:street') or tags.get('addr:street_official')
        if not housenumber or not street or lat is None or lon is None:
            return
        postcode_tag = tags.get('addr:postcode', '').strip()
        entry = {
            'osm_type':    osm_type,
            'osm_id':      osm_id,
            'street':      street,
            'housenumber': housenumber,
            'lat':         lat,
            'lon':         lon,
            'postcode_tag': postcode_tag or None,
        }
        if postcode_tag:
            self.with_postcode.append(entry)
        self.addresses.append(entry)

    def node(self, n):
        if n.location.valid():
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
                self._process('way', w.id, w.tags,
                              sum(lats)/len(lats), sum(lons)/len(lons))
        except Exception:
            pass


def load_osm_addresses(pbf_path):
    print('[OSM] Collecte des adresses...')
    h = AddressCollector()
    h.apply_file(pbf_path, locations=True)
    print(f'[OSM] {len(h.addresses)} adresses, '
          f'{len(h.with_postcode)} avec addr:postcode (anomalie)')
    return h.addresses, h.with_postcode


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def build_report(anomalies_postcode_tag, mismatches, no_postal_zone,
                 not_in_best, stats, best_date):
    today = date.today().isoformat()
    L = []
    L.append('=' * 72)
    L.append('RAPPORT DE COMPARAISON DES CODES POSTAUX PAR ADRESSE')
    L.append('Région de Bruxelles-Capitale — BeSt Address vs OpenStreetMap')
    L.append('=' * 72)
    L.append(f'Date du rapport      : {today}')
    L.append(f'Source BeSt (GPKG)   : publication {best_date}')
    L.append(f'Source OSM (PBF)     : {OSM_PBF_URL}')
    L.append('')

    L.append('RÉSUMÉ')
    L.append('-' * 40)
    L.append(f'  Adresses OSM analysées              : {stats["total"]:>6}')
    L.append(f'  Avec addr:postcode (anomalie)        : {stats["with_postcode_tag"]:>6}')
    L.append(f'  Hors zone boundary=postal_code OSM   : {stats["no_postal_zone"]:>6}')
    L.append(f'  Adresse absente du BeSt              : {stats["not_in_best"]:>6}')
    L.append(f'  CP OSM ≠ CP BeSt (à vérifier)        : {stats["mismatches"]:>6}')
    L.append(f'  CP OSM = CP BeSt (OK)                : {stats["ok"]:>6}')
    L.append('')

    L.append('ANOMALIE : ADRESSES AVEC addr:postcode DIRECT')
    L.append('(le tag addr:postcode ne devrait pas être utilisé à Bruxelles ;')
    L.append(' le code postal est porté par la relation boundary=postal_code)')
    L.append('-' * 40)
    if anomalies_postcode_tag:
        L.append(f'  {"OSM ref":<22} {"Rue":<33} {"N°":<8} {"addr:postcode"}')
        L.append(f'  {"-"*20:<22} {"-"*31:<33} {"-"*6:<8} {"-"*12}')
        for a in sorted(anomalies_postcode_tag, key=lambda x: x['street']):
            ref = f'{a["osm_type"]}/{a["osm_id"]}'
            L.append(f'  {ref:<22} {a["street"][:31]:<33} {a["housenumber"]:<8} {a["postcode_tag"]}')
    else:
        L.append('  (aucune)')
    L.append('')

    L.append('CP À VÉRIFIER : CP CALCULÉ OSM ≠ CP BeSt')
    L.append('-' * 40)
    if mismatches:
        L.append(f'  {"OSM ref":<22} {"Rue":<33} {"N°":<8} {"CP OSM":<8} {"CP BeSt"}')
        L.append(f'  {"-"*20:<22} {"-"*31:<33} {"-"*6:<8} {"-"*6:<8} {"-"*7}')
        for m in sorted(mismatches, key=lambda x: (x['cp_osm'], x['street'])):
            ref = f'{m["osm_type"]}/{m["osm_id"]}'
            L.append(f'  {ref:<22} {m["street"][:31]:<33} {m["housenumber"]:<8} '
                     f'{m["cp_osm"]:<8} {m["cp_best"]}')
    else:
        L.append('  (aucun mismatch)')
    L.append('')

    L.append('ADRESSES OSM HORS ZONE boundary=postal_code')
    L.append('-' * 40)
    if no_postal_zone:
        L.append(f'  {"OSM ref":<22} {"Rue":<33} {"N°":<8} {"CP BeSt"}')
        L.append(f'  {"-"*20:<22} {"-"*31:<33} {"-"*6:<8} {"-"*7}')
        for a in sorted(no_postal_zone, key=lambda x: x['street']):
            ref = f'{a["osm_type"]}/{a["osm_id"]}'
            L.append(f'  {ref:<22} {a["street"][:31]:<33} {a["housenumber"]:<8} '
                     f'{a.get("cp_best","?")}')
    else:
        L.append('  (aucune)')
    L.append('')

    L.append('ADRESSES OSM SANS CORRESPONDANCE DANS LE BeSt')
    L.append('(rue+numéro introuvable dans le GPKG BeSt)')
    L.append('-' * 40)
    if not_in_best:
        L.append(f'  {"OSM ref":<22} {"Rue":<33} {"N°":<8} {"CP OSM calculé"}')
        L.append(f'  {"-"*20:<22} {"-"*31:<33} {"-"*6:<8} {"-"*14}')
        for a in sorted(not_in_best, key=lambda x: x['street']):
            ref = f'{a["osm_type"]}/{a["osm_id"]}'
            L.append(f'  {ref:<22} {a["street"][:31]:<33} {a["housenumber"]:<8} '
                     f'{a.get("cp_osm","?")}')
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
    # 1. GPKG BeSt
    existing_gpkg = sorted(
        glob.glob('BeStBrussels_31370_GPKG_04000*.gpkg') +
        glob.glob('**/*.gpkg'),
        reverse=True
    )
    best_date = 'inconnue'

    if existing_gpkg:
        gpkg_path = existing_gpkg[0]
        print(f'[INFO] GPKG déjà présent : {gpkg_path}')
        m = re.search(r'(\d{8})', gpkg_path)
        if m:
            d = m.group(1)
            best_date = f'{d[:4]}-{d[4:6]}-{d[6:]}'
    else:
        latest_dt, latest_url = find_latest_best_gpkg_url()
        best_date = str(latest_dt)
        zip_name  = os.path.basename(latest_url)
        if not os.path.isfile(zip_name):
            download(latest_url, zip_name)
        gpkg_path = extract_gpkg(zip_name)

    # 2. PBF OSM
    if not os.path.isfile(OSM_PBF_FILE):
        download(OSM_PBF_URL, OSM_PBF_FILE)
    else:
        print(f'[INFO] PBF déjà présent : {OSM_PBF_FILE}')

    # 3. Polygones postal_code OSM
    postal_polygons, _ = build_postal_polygons(OSM_PBF_FILE)

    # 4. Adresses OSM
    osm_addresses, anomalies_postcode_tag = load_osm_addresses(OSM_PBF_FILE)

    # 5. Index BeSt
    best_index = load_best_index(gpkg_path)

    # 6. Analyse
    print('[ANALYSE] Calcul spatial et comparaison CP...')
    prepared_cache = {}
    mismatches     = []
    no_postal_zone = []
    not_in_best    = []
    ok_count       = 0

    for i, addr in enumerate(osm_addresses):
        if i % 10000 == 0:
            print(f'\r    {i}/{len(osm_addresses)}', end='', flush=True)
        cp_osm  = find_postal_code(addr['lon'], addr['lat'],
                                   postal_polygons, prepared_cache)
        cp_best = lookup_best_zipcode(addr['street'], addr['housenumber'],
                                      best_index)
        addr['cp_osm']  = cp_osm
        addr['cp_best'] = cp_best

        if cp_osm is None:
            no_postal_zone.append(addr)
            continue
        if cp_best is None:
            not_in_best.append(addr)
            continue
        if cp_osm != cp_best:
            mismatches.append(addr)
        else:
            ok_count += 1

    print(f'\r    {len(osm_addresses)}/{len(osm_addresses)}')
    print('[ANALYSE] Terminé.')

    stats = {
        'total':             len(osm_addresses),
        'with_postcode_tag': len(anomalies_postcode_tag),
        'no_postal_zone':    len(no_postal_zone),
        'not_in_best':       len(not_in_best),
        'mismatches':        len(mismatches),
        'ok':                ok_count,
    }

    report = build_report(
        anomalies_postcode_tag=anomalies_postcode_tag,
        mismatches=mismatches,
        no_postal_zone=no_postal_zone,
        not_in_best=not_in_best,
        stats=stats,
        best_date=best_date,
    )

    output_file = f'postal_code_report_{date.today().isoformat()}.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\n[OK] Rapport écrit : {output_file}')
