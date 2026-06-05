#!/usr/bin/env python3
"""
compare-postal-codes.py

Pour chaque adresse OSM dans la région bruxelloise :
  1. Si addr:postcode est présent → loggé en anomalie, le code postal
     est quand même calculé spatialement (on ignore addr:postcode)
  2. Code postal calculé spatialement (point-in-polygon dans les relations
     boundary=postal_code OSM)
  3. Match avec le code postal BeSt (haspostalinfo_objectidentifier) via
     join spatial sur (lon, lat) + numéro normalisé
  4. Si mismatch → inclus dans le rapport "CP à vérifier"

En plus du rapport texte, le script exporte un GeoJSON par code postal OSM
(plus un combiné) dans `postal_codes_geojson/` pour debug visuel
(JOSM, QGIS, geojson.io…).

Source BeSt : GPKG sectionID=04000, URL directe.
Source OSM  : PBF Brussels daily.
Sortie      : postal_code_report_YYYY-MM-DD.txt
              postal_codes_geojson/postal_code_XXXX.geojson  (un par CP)
              postal_codes_geojson/_all_postal_codes.geojson (combiné)
"""

import sys
import os
import glob
import json
import time
import urllib.request
import urllib.error
import zipfile
import unicodedata
import re
from datetime import datetime, date, timedelta

# En CI (GitHub Actions), stdout est block-bufferisé : sans ça les prints
# ne s'affichent qu'à la fin du script (ou jamais, si on est tué avant).
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except AttributeError:
    pass  # Python < 3.7
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union
from shapely.prepared import prep
import geopandas as gpd
import osmium

GPKG_BASE_URL = 'https://urbisdownload.datastore.brussels/BeSt/FullDownload/GPKG/BeStBrussels_31370_GPKG_04000_{date}.zip'
OSM_PBF_URL   = 'https://raw.githubusercontent.com/PasLoin/Osm-python-analyse_Belgium/main/pbf_analyse/history/Brussels-daily.pbf'
OSM_PBF_FILE  = 'brussels_capital_region-latest.osm.pbf'
HEADERS       = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}

GEOJSON_DIR   = 'postal_codes_geojson'

# Polygone officiel de la Région de Bruxelles-Capitale.
# Le PBF est généré avec un buffer (~100m) autour de cette région, donc :
#   - certaines adresses du PBF sont hors région → à filtrer
#   - certaines relations boundary=postal_code touchent juste le bord
#     (ex: 1800 Vilvoorde, relation 3366255) : seules quelques ways sont
#     présentes, le polygone est reconstruit avec une "ligne droite imaginaire"
#     et déborde sur des CP voisins (1120) → à rejeter
BOUNDARY_RELATION_ID = 54094
BOUNDARY_POLY_URL    = f'https://polygons.openstreetmap.fr/get_poly.py?id={BOUNDARY_RELATION_ID}'
REGION_POLY_CACHE    = f'region_{BOUNDARY_RELATION_ID}.poly'

# La whitelist des CP légitimes est construite dynamiquement depuis BeSt
# (cf. load_best_spatial_index) — elle inclut automatiquement les codes
# postaux spéciaux (parlement, institutions...) qui ne sont pas dans la
# liste classique des 19 communes.


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

def find_latest_best_gpkg_url(max_days=60,
                              per_request_timeout=10,
                              total_timeout=180,
                              max_consecutive_timeouts=5):
    """
    Cherche le GPKG 04000 le plus récent en testant les dates des `max_days`
    derniers jours via une requête HEAD.

    Affiche pour chaque date :
      - le code HTTP retourné, OU
      - l'exception (timeout, DNS, connexion refusée, ...)

    Abandonne :
      - après `total_timeout` secondes au total
      - après `max_consecutive_timeouts` timeouts d'affilée (serveur probablement down)
      - après `max_days` tentatives infructueuses
    """
    print(f'[BeSt] Recherche du GPKG 04000 le plus récent', flush=True)
    print(f'[BeSt]   max_days={max_days}, '
          f'per_request_timeout={per_request_timeout}s, '
          f'total_timeout={total_timeout}s', flush=True)
    print(f'[BeSt]   URL pattern: {GPKG_BASE_URL}', flush=True)

    today = date.today()
    start = time.monotonic()
    consecutive_timeouts = 0

    for delta in range(max_days):
        elapsed = time.monotonic() - start
        if elapsed > total_timeout:
            print(f'[BeSt] ⏱  Timeout global atteint ({elapsed:.0f}s > {total_timeout}s) — abandon.',
                  flush=True)
            break

        d = today - timedelta(days=delta)
        date_str = d.strftime('%Y%m%d')
        url = GPKG_BASE_URL.format(date=date_str)
        prefix = f'[BeSt] [{delta+1:02d}/{max_days}] {date_str}'

        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, method='HEAD', headers=HEADERS)
            with urllib.request.urlopen(req, timeout=per_request_timeout) as r:
                dt = time.monotonic() - t0
                status = r.status
                if status == 200:
                    size = r.headers.get('Content-Length', '?')
                    print(f'{prefix} → HTTP 200 ✓ ({dt:.1f}s, Content-Length={size}) — TROUVÉ',
                          flush=True)
                    print(f'[BeSt] URL : {url}', flush=True)
                    return d, url
                else:
                    print(f'{prefix} → HTTP {status} ({dt:.1f}s)', flush=True)
                    consecutive_timeouts = 0

        except urllib.error.HTTPError as e:
            dt = time.monotonic() - t0
            print(f'{prefix} → HTTP {e.code} {e.reason} ({dt:.1f}s)', flush=True)
            consecutive_timeouts = 0

        except urllib.error.URLError as e:
            dt = time.monotonic() - t0
            reason = e.reason
            is_timeout = isinstance(reason, TimeoutError) or 'timed out' in str(reason).lower()
            print(f'{prefix} → URLError: {reason} ({dt:.1f}s)', flush=True)
            if is_timeout:
                consecutive_timeouts += 1
            else:
                consecutive_timeouts = 0

        except TimeoutError as e:
            dt = time.monotonic() - t0
            print(f'{prefix} → TimeoutError ({dt:.1f}s)', flush=True)
            consecutive_timeouts += 1

        except Exception as e:
            dt = time.monotonic() - t0
            print(f'{prefix} → {type(e).__name__}: {e} ({dt:.1f}s)', flush=True)
            consecutive_timeouts = 0  # autre erreur, on ne compte pas comme timeout

        if consecutive_timeouts >= max_consecutive_timeouts:
            print(f'[BeSt] ⚠  {consecutive_timeouts} timeouts consécutifs — '
                  f'le serveur urbisdownload.datastore.brussels semble indisponible. Abandon.',
                  flush=True)
            break

    print(f'[ERREUR] Aucun GPKG 04000 trouvé après {delta+1} tentatives '
          f'({time.monotonic()-start:.0f}s écoulés).', flush=True)
    sys.exit(1)


def download(url, dest):
    print(f'[DL] Téléchargement de {os.path.basename(url)}...', flush=True)
    print(f'[DL]   URL: {url}', flush=True)
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get('Content-Length', 0))
        print(f'[DL]   HTTP {r.status}, Content-Length={total} bytes', flush=True)
        downloaded = 0
        last_pct_logged = -5
        with open(dest, 'wb') as f:
            while chunk := r.read(65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = min(downloaded * 100 // total, 100)
                    # Log un newline tous les 10% (compatible CI, contrairement à \r)
                    if pct >= last_pct_logged + 10:
                        print(f'[DL]   {pct:3d}%  ({downloaded/1_000_000:.1f}/{total/1_000_000:.1f} MB)',
                              flush=True)
                        last_pct_logged = pct
    dt = time.monotonic() - t0
    print(f'[DL] Sauvegardé : {dest} ({downloaded/1_000_000:.1f} MB en {dt:.1f}s)', flush=True)


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
# BeSt : index spatial (lon_wgs84, lat_wgs84, norm_housenumber) → postal_code
# ---------------------------------------------------------------------------

from scipy.spatial import cKDTree
import numpy as np
from pyproj import Transformer

_TRANSFORMER = Transformer.from_crs("EPSG:31370", "EPSG:4326", always_xy=True)


def load_best_spatial_index(gpkg_path):
    """
    Retourne (kdtree, lons, lats, norm_nbrs, postcodes) sur les adresses BeSt current.
    KDTree indexé sur (lon, lat) WGS84.
    """
    print(f'[BeSt] Lecture spatiale de {gpkg_path}...')
    addr_gdf = gpd.read_file(gpkg_path, layer='BrusselsAddressL72_04000')
    if 'status' in addr_gdf.columns:
        addr_gdf = addr_gdf[addr_gdf['status'].str.lower().str.contains('current', na=False)]

    lons, lats, norm_nbrs, postcodes = [], [], [], []
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
        x = row.get('x')
        y = row.get('y')
        if x is None or y is None or (x == 0 and y == 0):
            skipped += 1
            continue
        try:
            lon, lat = _TRANSFORMER.transform(float(x), float(y))
        except Exception:
            skipped += 1
            continue
        lons.append(lon)
        lats.append(lat)
        norm_nbrs.append(normalize(nbr))
        postcodes.append(pc)

    lons = np.array(lons)
    lats = np.array(lats)
    coords = np.column_stack([lons, lats])
    tree = cKDTree(coords)
    print(f'[BeSt] {len(lons)} adresses indexées ({skipped} ignorées)')

    brussels_postal_codes = frozenset(postcodes)
    print(f'[BeSt] {len(brussels_postal_codes)} codes postaux distincts dans BeSt : '
          f'{sorted(brussels_postal_codes)}', flush=True)
    return tree, lons, lats, norm_nbrs, postcodes, brussels_postal_codes


# Rayon de recherche en degrés (~50m à Bruxelles : 0.00045°)
_SEARCH_RADIUS_DEG = 0.00045


def lookup_best_zipcode(lon, lat, norm_nbr, tree, lons, lats, norm_nbrs, postcodes):
    """
    Cherche dans le KDTree BeSt le point le plus proche du point OSM (lon, lat)
    ayant le même numéro normalisé, dans un rayon de 50m.
    Retourne le code postal BeSt ou None.
    """
    idxs = tree.query_ball_point([lon, lat], r=_SEARCH_RADIUS_DEG)
    if not idxs:
        return None
    matches = [i for i in idxs if norm_nbrs[i] == norm_nbr]
    if not matches:
        return None
    best = min(matches, key=lambda i: (lons[i]-lon)**2 + (lats[i]-lat)**2)
    return postcodes[best]


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
    segs = [list(s) for s in segments if len(s) >= 2]
    rings = []

    while segs:
        ring = list(segs.pop(0))
        changed = True
        while changed:
            changed = False
            for i, seg in enumerate(segs):
                if not seg:
                    continue
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
        if len(ring) >= 3 and not _close_enough(ring[0], ring[-1]):
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)

    return rings


def _close_enough(p1, p2, tol=1e-7):
    return abs(p1[0]-p2[0]) < tol and abs(p1[1]-p2[1]) < tol


def _safe_polygon(coords):
    """Construit un Polygon valide depuis une liste de coords, en réparant si besoin."""
    try:
        p = Polygon(coords)
    except Exception:
        return None
    if not p.is_valid:
        p = p.buffer(0)
    if p.is_empty:
        return None
    return p


# ---------------------------------------------------------------------------
# Polygone de la Région de Bruxelles-Capitale (filtre buffer + clip CP)
# ---------------------------------------------------------------------------

def _parse_poly_file(text):
    """
    Parse le format Osmosis .poly servi par polygons.openstreetmap.fr.
    Retourne une liste de (is_hole: bool, ring: [(lon, lat), ...]).
    Format : https://wiki.openstreetmap.org/wiki/Osmosis/Polygon_Filter_File_Format
    """
    rings = []
    state = 'header'   # header → between_sections → in_section → ...
    is_hole = False
    current = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if state == 'header':
            # 1re ligne non vide = identifiant du fichier, on l'ignore
            state = 'between_sections'
            continue
        if state == 'between_sections':
            if line == 'END':
                break  # fin du fichier
            is_hole = line.startswith('!')
            current = []
            state = 'in_section'
            continue
        if state == 'in_section':
            if line == 'END':
                if len(current) >= 3:
                    rings.append((is_hole, current))
                state = 'between_sections'
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    current.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    pass
    return rings


def _build_region_polygon(rings):
    """Construit un (Multi)Polygon Shapely depuis les rings .poly."""
    if not rings:
        return None

    outers, holes = [], []
    for is_hole, ring in rings:
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring = list(ring) + [ring[0]]
        (holes if is_hole else outers).append(ring)

    polys = []
    for outer in outers:
        outer_poly = _safe_polygon(outer)
        if outer_poly is None or outer_poly.geom_type != 'Polygon':
            continue
        applicable_holes = []
        for hole in holes:
            hp = _safe_polygon(hole)
            if hp is not None and outer_poly.contains(hp):
                applicable_holes.append(hole)
        if applicable_holes:
            try:
                p = Polygon(outer, applicable_holes)
                if not p.is_valid:
                    p = p.buffer(0)
                polys.append(p if not p.is_empty else outer_poly)
            except Exception:
                polys.append(outer_poly)
        else:
            polys.append(outer_poly)

    if not polys:
        return None
    return polys[0] if len(polys) == 1 else unary_union(polys)


def fetch_region_polygon():
    """
    Récupère le polygone de la RBC depuis polygons.openstreetmap.fr.
    Avec cache local et retry simple.
    """
    if os.path.isfile(REGION_POLY_CACHE):
        print(f'[REGION] Cache trouvé : {REGION_POLY_CACHE}', flush=True)
        with open(REGION_POLY_CACHE, 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        print(f'[REGION] Téléchargement : {BOUNDARY_POLY_URL}', flush=True)
        last_err = None
        text = None
        for attempt in range(3):
            t0 = time.monotonic()
            try:
                req = urllib.request.Request(BOUNDARY_POLY_URL, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=60) as r:
                    text = r.read().decode('utf-8', errors='replace')
                dt = time.monotonic() - t0
                print(f'[REGION] Tentative {attempt+1} → HTTP {r.status} '
                      f'({len(text)} bytes en {dt:.1f}s)', flush=True)
                # Sanity-check : un vrai .poly contient au moins un "END"
                if 'END' in text and len(text) > 100:
                    break
                print(f'[REGION] Réponse suspecte (pas un .poly valide), retry...',
                      flush=True)
                text = None
            except Exception as e:
                last_err = e
                print(f'[REGION] Tentative {attempt+1} échouée : '
                      f'{type(e).__name__}: {e}', flush=True)
                time.sleep(2)
        if text is None:
            print(f'[ERREUR] Impossible de récupérer le polygone Région ({last_err})',
                  flush=True)
            sys.exit(1)
        with open(REGION_POLY_CACHE, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'[REGION] Sauvegardé dans le cache : {REGION_POLY_CACHE}', flush=True)

    rings = _parse_poly_file(text)
    print(f'[REGION] {len(rings)} ring(s) parsé(s) '
          f'({sum(1 for h,_ in rings if not h)} outer, '
          f'{sum(1 for h,_ in rings if h)} hole)', flush=True)
    poly = _build_region_polygon(rings)
    if poly is None or poly.is_empty:
        print('[ERREUR] Polygone Région invalide ou vide.', flush=True)
        sys.exit(1)
    print(f'[REGION] Polygone construit : type={poly.geom_type}, '
          f'area={poly.area:.6f} deg² (~{poly.area * 12321:.1f} km² approx)',
          flush=True)
    return poly


def filter_postal_polygons_to_region(postal_polygons, region_poly, whitelist):
    """
    1. Rejette tout polygone dont le code postal n'est pas dans `whitelist`
       (typiquement l'ensemble des CP distincts du GPKG BeSt) → gomme
       les 1800, 1830, 1850 etc. mal reconstruits depuis le PBF tampon.
    2. Clip les polygones gardés à la Région (gomme les débordements de bord).
    """
    filtered = {}
    rejected_whitelist = []
    rejected_clip      = []

    for pc, geom in postal_polygons.items():
        if pc not in whitelist:
            rejected_whitelist.append(pc)
            continue
        try:
            clipped = geom.intersection(region_poly)
            if not clipped.is_valid:
                clipped = clipped.buffer(0)
        except Exception as e:
            print(f'[REGION] CP {pc}: intersection échouée ({e}), gardé brut',
                  flush=True)
            filtered[pc] = geom
            continue
        if clipped.is_empty:
            rejected_clip.append(pc)
            continue
        filtered[pc] = clipped

    if rejected_whitelist:
        print(f'[REGION] {len(rejected_whitelist)} CP hors whitelist BeSt rejetés : '
              f'{sorted(rejected_whitelist)}', flush=True)
    if rejected_clip:
        print(f'[REGION] {len(rejected_clip)} CP rejetés (clip vide) : '
              f'{sorted(rejected_clip)}', flush=True)
    print(f'[REGION] {len(filtered)} polygones CP gardés sur '
          f'{len(postal_polygons)}', flush=True)
    return filtered


def build_postal_polygons(pbf_path):
    """
    Construit les polygones boundary=postal_code à partir du PBF.
    Assigne correctement chaque inner ring à l'outer qui le contient.
    """
    print('[PC] Collecte des relations boundary=postal_code...')
    handler = PostalCodeHandler()
    handler.apply_file(pbf_path, locations=True)
    print(f'[PC] {len(handler.relations)} relations trouvées')
    if not handler.relations:
        return {}, {}

    postal_polygons = {}
    for pc, way_refs in handler.relations.items():
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
            print(f'[WARN] CP {pc} : aucun way outer dans la relation')
            continue

        try:
            outer_rings = _chain_ways(outer_segs)
            inner_rings = _chain_ways(inner_segs)

            if not outer_rings:
                print(f'[WARN] CP {pc} : impossible d\'assembler les rings outer')
                continue

            # Convertir les inner rings en polygones une fois pour all (pour test de containment)
            inner_polys = []
            for iring in inner_rings:
                ip = _safe_polygon(iring)
                if ip is not None and ip.geom_type == 'Polygon':
                    inner_polys.append(ip)

            polys = []
            for oring in outer_rings:
                outer_poly = _safe_polygon(oring)
                if outer_poly is None:
                    continue

                # Assigner UNIQUEMENT les inner rings contenus dans CET outer
                holes_coords = []
                for ip in inner_polys:
                    if outer_poly.contains(ip):
                        try:
                            holes_coords.append(list(ip.exterior.coords))
                        except AttributeError:
                            pass  # buffer(0) a transformé en MultiPolygon, on ignore

                if holes_coords:
                    try:
                        p = Polygon(outer_poly.exterior.coords, holes_coords)
                        if not p.is_valid:
                            p = p.buffer(0)
                        if p.is_empty:
                            p = outer_poly
                    except Exception:
                        p = outer_poly
                else:
                    p = outer_poly

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


def export_postal_polygons_geojson(postal_polygons, relation_ids,
                                   region_poly=None, output_dir=GEOJSON_DIR):
    """
    Debug : exporte chaque polygone postal_code OSM en GeoJSON séparé,
    plus un fichier combiné `_all_postal_codes.geojson`.
    À ouvrir dans QGIS, JOSM, geojson.io, …
    """
    if not postal_polygons:
        print('[GEOJSON] Aucun polygone à exporter.')
        return

    os.makedirs(output_dir, exist_ok=True)

    records = []
    for pc in sorted(postal_polygons.keys()):
        geom = postal_polygons[pc]
        rel_id = relation_ids.get(pc)
        props = {
            'postal_code':    pc,
            'osm_relation_id': rel_id,
            'osm_url':        f'https://www.openstreetmap.org/relation/{rel_id}' if rel_id else None,
            'geometry_type': geom.geom_type,
            'area_deg2':     round(geom.area, 8),
        }
        # Fichier individuel
        try:
            gdf = gpd.GeoDataFrame([props], geometry=[geom], crs='EPSG:4326')
            out_path = os.path.join(output_dir, f'postal_code_{pc}.geojson')
            gdf.to_file(out_path, driver='GeoJSON')
        except Exception as e:
            print(f'[WARN] Export GeoJSON {pc} échoué : {e}')
            continue
        records.append((props, geom))

    # Fichier combiné
    if records:
        try:
            gdf = gpd.GeoDataFrame(
                [r[0] for r in records],
                geometry=[r[1] for r in records],
                crs='EPSG:4326',
            )
            combined_path = os.path.join(output_dir, '_all_postal_codes.geojson')
            gdf.to_file(combined_path, driver='GeoJSON')
        except Exception as e:
            print(f'[WARN] Export GeoJSON combiné échoué : {e}')

    # Polygone de la Région (pour overlay visuel sur les CP)
    if region_poly is not None:
        try:
            gdf = gpd.GeoDataFrame(
                [{'name': 'Région de Bruxelles-Capitale',
                  'osm_relation_id': BOUNDARY_RELATION_ID,
                  'source': BOUNDARY_POLY_URL}],
                geometry=[region_poly],
                crs='EPSG:4326',
            )
            gdf.to_file(os.path.join(output_dir, '_region_brussels.geojson'),
                        driver='GeoJSON')
        except Exception as e:
            print(f'[WARN] Export GeoJSON région échoué : {e}', flush=True)

    print(f'[GEOJSON] {len(records)} polygones exportés dans {output_dir}/')


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
        self.multi_count   = 0  # nb d'adresses issues d'éclatement "24;30"

    def _process(self, osm_type, osm_id, tags, lat, lon):
        housenumber_raw = tags.get('addr:housenumber')
        street      = tags.get('addr:street') or tags.get('addr:street_official')
        if not housenumber_raw or not street or lat is None or lon is None:
            return
        postcode_tag = tags.get('addr:postcode', '').strip()

        # Convention OSM : addr:housenumber="24;30" représente UNE porte qui
        # regroupe DEUX adresses postales (24 et 30). Idem "1068;1070;1072".
        # On émet une entrée par numéro distinct, en conservant la trace
        # de l'osm_id partagé pour pouvoir retrouver l'objet en cas d'anomalie.
        housenumbers = [h.strip() for h in str(housenumber_raw).split(';') if h.strip()]
        if not housenumbers:
            return
        is_multi = len(housenumbers) > 1

        for hn in housenumbers:
            entry = {
                'osm_type':    osm_type,
                'osm_id':      osm_id,
                'street':      street,
                'housenumber': hn,
                'housenumber_raw': housenumber_raw if is_multi else None,
                'lat':         lat,
                'lon':         lon,
                'postcode_tag': postcode_tag or None,
            }
            if postcode_tag:
                self.with_postcode.append(entry)
            self.addresses.append(entry)
            if is_multi:
                self.multi_count += 1

    def node(self, n):
        if n.location.valid():
            self._process('node', n.id, n.tags, n.location.lat, n.location.lon)

    def way(self, w):
        if not w.tags.get('addr:housenumber'):
            return
        try:
            coords = []
            for nd in w.nodes:
                if nd.location.valid():
                    coords.append((nd.location.lon, nd.location.lat))
            if len(coords) < 2:
                return

            # Way fermée (premier == dernier nœud) → polygone (typiquement
            # un bâtiment). On utilise le vrai centroïde géométrique, pas la
            # moyenne arithmétique des nœuds (qui peut tomber très à côté pour
            # un L, un U ou un polygone non-convexe).
            # Way ouverte → on prend le centroïde de la LineString (point
            # médian le long du tracé).
            geom = None
            if coords[0] == coords[-1] and len(coords) >= 4:
                try:
                    geom = Polygon(coords)
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                    if geom.is_empty:
                        geom = None
                except Exception:
                    geom = None
            if geom is None:
                geom = LineString(coords)

            c = geom.centroid
            if c.is_empty:
                return
            # _process attend (lat, lon)
            self._process('way', w.id, w.tags, c.y, c.x)
        except Exception:
            pass


def load_osm_addresses(pbf_path):
    print('[OSM] Collecte des adresses...', flush=True)
    h = AddressCollector()
    h.apply_file(pbf_path, locations=True)
    print(f'[OSM] {len(h.addresses)} adresses, '
          f'{len(h.with_postcode)} avec addr:postcode (anomalie), '
          f'{h.multi_count} issues d\'un addr:housenumber multi (ex: "24;30")',
          flush=True)
    return h.addresses, h.with_postcode


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def build_report(anomalies_postcode_tag, mismatches, no_postal_zone,
                 outside_region, stats, best_date):
    today = date.today().isoformat()
    L = []
    L.append('=' * 72)
    L.append('RAPPORT DE COMPARAISON DES CODES POSTAUX PAR ADRESSE')
    L.append('Région de Bruxelles-Capitale — BeSt Address vs OpenStreetMap')
    L.append('=' * 72)
    L.append(f'Date du rapport      : {today}')
    L.append(f'Source BeSt (GPKG)   : publication {best_date}')
    L.append(f'Source OSM (PBF)     : {OSM_PBF_URL}')
    L.append(f'Polygone Région      : {BOUNDARY_POLY_URL}')
    L.append('')

    L.append('RÉSUMÉ')
    L.append('-' * 40)
    L.append(f'  Codes postaux dans BeSt (whitelist)  : {stats["best_postal_codes"]:>6}')
    L.append(f'  Polygones CP OSM gardés              : {stats["osm_postal_codes"]:>6}')
    L.append('')
    L.append(f'  Adresses OSM trouvées dans le PBF    : {stats["total_pbf"]:>6}')
    L.append(f'    └─ issues d\'un addr:housenumber    : {stats["multi_housenumber"]:>6}')
    L.append(f'       multi ("24;30" → 24 + 30)')
    L.append(f'    └─ dans le buffer (hors région)    : {stats["outside_region"]:>6}')
    L.append(f'  Adresses OSM analysées (intra-RBC)   : {stats["total"]:>6}')
    L.append(f'    Avec addr:postcode (anomalie)      : {stats["with_postcode_tag"]:>6}')
    L.append(f'    Hors zone boundary=postal_code OSM : {stats["no_postal_zone"]:>6}')
    L.append(f'    CP OSM ≠ CP BeSt (à vérifier)      : {stats["mismatches"]:>6}')
    L.append(f'    CP OSM = CP BeSt (OK)              : {stats["ok"]:>6}')
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

    L.append('=' * 72)
    L.append('FIN DU RAPPORT')
    L.append('=' * 72)
    return '\n'.join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f'[START] {datetime.now().isoformat(timespec="seconds")} — '
          f'compare-postal-codes.py', flush=True)
    print(f'[START] Python {sys.version.split()[0]}, cwd={os.getcwd()}', flush=True)

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

    # 3. Index spatial BeSt + whitelist dynamique des CP légitimes
    best_tree, best_lons, best_lats, best_norm_nbrs, best_postcodes, \
        brussels_postal_codes = load_best_spatial_index(gpkg_path)

    # 4. Polygones postal_code OSM (bruts, avant filtrage région)
    postal_polygons_raw, relation_ids = build_postal_polygons(OSM_PBF_FILE)

    # 5. Polygone officiel de la Région de Bruxelles-Capitale
    region_poly = fetch_region_polygon()
    region_prep = prep(region_poly)

    # 6. Filtrer les polygones CP : whitelist (BeSt) + clip à la Région
    postal_polygons = filter_postal_polygons_to_region(
        postal_polygons_raw, region_poly, brussels_postal_codes)

    # 6bis. Export GeoJSON debug (un par CP + combiné + polygone Région)
    export_postal_polygons_geojson(postal_polygons, relation_ids,
                                   region_poly=region_poly)

    # 7. Adresses OSM (toutes, y compris celles du buffer)
    osm_addresses_all, anomalies_all = load_osm_addresses(OSM_PBF_FILE)

    # 7bis. Ne garder que les adresses strictement dans la Région
    print('[REGION] Filtrage des adresses (élimination du buffer du PBF)...',
          flush=True)
    osm_addresses  = []
    outside_region = []
    for addr in osm_addresses_all:
        if region_prep.covers(Point(addr['lon'], addr['lat'])):
            osm_addresses.append(addr)
        else:
            outside_region.append(addr)
    anomalies_postcode_tag = [a for a in anomalies_all
                              if region_prep.covers(Point(a['lon'], a['lat']))]
    print(f'[REGION] {len(osm_addresses)}/{len(osm_addresses_all)} adresses '
          f'gardées ({len(outside_region)} dans le buffer)', flush=True)

    # 8. Analyse
    print('[ANALYSE] Calcul spatial et comparaison CP...', flush=True)
    prepared_cache = {}
    mismatches     = []
    no_postal_zone = []
    not_in_best_count = 0  # compteur uniquement (log), pas exporté dans le rapport
    ok_count       = 0

    for i, addr in enumerate(osm_addresses):
        if i % 10000 == 0:
            print(f'[ANALYSE]   {i}/{len(osm_addresses)}', flush=True)
        cp_osm  = find_postal_code(addr['lon'], addr['lat'],
                                   postal_polygons, prepared_cache)
        norm_nbr = normalize(addr['housenumber'])
        cp_best = lookup_best_zipcode(
            addr['lon'], addr['lat'], norm_nbr,
            best_tree, best_lons, best_lats, best_norm_nbrs, best_postcodes
        )
        addr['cp_osm']  = cp_osm
        addr['cp_best'] = cp_best

        if cp_osm is None:
            no_postal_zone.append(addr)
            continue
        if cp_best is None:
            not_in_best_count += 1
            continue
        if cp_osm != cp_best:
            mismatches.append(addr)
        else:
            ok_count += 1

    print(f'[ANALYSE]   {len(osm_addresses)}/{len(osm_addresses)}', flush=True)
    print(f'[ANALYSE] Terminé. {not_in_best_count} adresses ignorées '
          f'(rue+numéro absent de BeSt — couvert par un autre rapport).',
          flush=True)

    # Comptage des adresses issues d'un éclatement housenumber multi
    multi_count = sum(1 for a in osm_addresses_all if a.get('housenumber_raw'))

    stats = {
        'best_postal_codes': len(brussels_postal_codes),
        'osm_postal_codes':  len(postal_polygons),
        'total_pbf':         len(osm_addresses_all),
        'multi_housenumber': multi_count,
        'outside_region':    len(outside_region),
        'total':             len(osm_addresses),
        'with_postcode_tag': len(anomalies_postcode_tag),
        'no_postal_zone':    len(no_postal_zone),
        'mismatches':        len(mismatches),
        'ok':                ok_count,
    }

    report = build_report(
        anomalies_postcode_tag=anomalies_postcode_tag,
        mismatches=mismatches,
        no_postal_zone=no_postal_zone,
        outside_region=outside_region,
        stats=stats,
        best_date=best_date,
    )

    output_file = f'postal_code_report_{date.today().isoformat()}.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\n[OK] Rapport écrit : {output_file}')
