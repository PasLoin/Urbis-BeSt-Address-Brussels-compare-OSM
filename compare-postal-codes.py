#!/usr/bin/env python3
"""
compare-postal-codes.py

Compare les codes postaux présents dans OSM (via les relations boundary=postal_code)
avec les codes postaux attendus depuis le fichier UrbIS (INSPIRE Addresses GPKG).

Spécificité bruxelloise : les adresses UrbIS ne portent pas toujours de code postal
directement exploitable dans le GPKG. On les regroupe par ZIPCODE quand disponible.
Côté OSM, les codes postaux sont portés par des relations de type :
  type=boundary + boundary=postal_code + postal_code=XXXX

Sortie : rapport texte dans postal_code_report_YYYY-MM-DD.txt
"""

import sys
import os
import glob
import json
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, date

import geopandas as gpd
import osmium

FEED_URL = 'https://urbisdownload.datastore.brussels/atomfeed/2cf42541-1813-11ef-8a81-00090ffe0001-en.xml'
OSM_PBF_URL = 'https://raw.githubusercontent.com/PasLoin/Osm-python-analyse_Belgium/main/pbf_analyse/history/Brussels-daily.pbf'
OSM_PBF_FILE = 'brussels_capital_region-latest.osm.pbf'
ATOM_NS = 'http://www.w3.org/2005/Atom'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}


# ---------------------------------------------------------------------------
# Fetch helpers (réutilisées depuis fetch-latest.py)
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
        cwd = os.path.abspath('.')
        if not out_path.startswith(cwd + os.sep):
            print('[ERREUR] Nom de fichier .gpkg invalide dans le ZIP.')
            sys.exit(1)
        z.extract(gpkg_name, '.')
        print(f'[ZIP] Extrait : {gpkg_name}')
        return gpkg_name


# ---------------------------------------------------------------------------
# UrbIS : extraction des codes postaux depuis le GPKG
# ---------------------------------------------------------------------------

def load_urbis_postal_codes(gpkg_path):
    """
    Lit la couche 'Addresses' et retourne un set de codes postaux (str).
    Filtre les entrées sans PARENTID (adresses principales uniquement).
    """
    print(f'[URBIS] Lecture de {gpkg_path}...')
    gdf = gpd.read_file(gpkg_path, layer='Addresses')
    gdf = gdf[gdf['PARENTID'].isna()].copy()

    # Le champ ZIPCODE peut être int, float ou str selon le GPKG
    raw = gdf['ZIPCODE'].dropna()
    postal_codes = set()
    for val in raw:
        s = str(val).strip()
        # Supprimer les décimales éventuelles (ex: "1000.0" → "1000")
        if s.endswith('.0'):
            s = s[:-2]
        if s.isdigit() and len(s) == 4:
            postal_codes.add(s)

    # Statistiques par code postal
    stats = {}
    for val in raw:
        s = str(val).strip()
        if s.endswith('.0'):
            s = s[:-2]
        if s.isdigit() and len(s) == 4:
            stats[s] = stats.get(s, 0) + 1

    print(f'[URBIS] {len(postal_codes)} codes postaux distincts trouvés')
    return postal_codes, stats


# ---------------------------------------------------------------------------
# OSM : extraction des codes postaux depuis les relations boundary=postal_code
# ---------------------------------------------------------------------------

class PostalCodeRelationHandler(osmium.SimpleHandler):
    """
    Parcourt toutes les relations OSM.
    Retient celles qui ont :
      type=boundary
      boundary=postal_code
      postal_code=XXXX   (ou ref=XXXX comme fallback)
    """

    def __init__(self):
        super().__init__()
        self.postal_codes = set()
        self.details = []   # liste de dicts pour le rapport détaillé

    def relation(self, r):
        tags = r.tags
        if tags.get('type') != 'boundary':
            return
        if tags.get('boundary') != 'postal_code':
            return

        pc = tags.get('postal_code') or tags.get('ref') or ''
        pc = pc.strip()
        if not pc:
            return

        # Normalisation : garder uniquement les codes à 4 chiffres
        if pc.isdigit() and len(pc) == 4:
            self.postal_codes.add(pc)
            self.details.append({
                'osm_id': r.id,
                'postal_code': pc,
                'name': tags.get('name', ''),
                'name_fr': tags.get('name:fr', ''),
                'name_nl': tags.get('name:nl', ''),
            })


def load_osm_postal_codes(pbf_path):
    print(f'[OSM] Lecture des relations boundary=postal_code dans {pbf_path}...')
    handler = PostalCodeRelationHandler()
    handler.apply_file(pbf_path)
    print(f'[OSM] {len(handler.postal_codes)} codes postaux trouvés dans OSM')
    return handler.postal_codes, handler.details


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def build_report(
    urbis_codes: set,
    urbis_stats: dict,
    osm_codes: set,
    osm_details: list,
    urbis_date: str,
    osm_pbf_url: str,
) -> str:
    today = date.today().isoformat()

    only_in_urbis = sorted(urbis_codes - osm_codes)
    only_in_osm = sorted(osm_codes - urbis_codes)
    in_both = sorted(urbis_codes & osm_codes)

    osm_detail_map = {d['postal_code']: d for d in osm_details}

    lines = []
    lines.append('=' * 72)
    lines.append('RAPPORT DE COMPARAISON DES CODES POSTAUX')
    lines.append('Région de Bruxelles-Capitale — UrbIS vs OpenStreetMap')
    lines.append('=' * 72)
    lines.append(f'Date du rapport          : {today}')
    lines.append(f'Source UrbIS (GPKG)      : date de publication {urbis_date}')
    lines.append(f'Source OSM (PBF)         : {osm_pbf_url}')
    lines.append('')
    lines.append('RÉSUMÉ')
    lines.append('-' * 40)
    lines.append(f'  Codes postaux UrbIS                : {len(urbis_codes):>4}')
    lines.append(f'  Codes postaux OSM (relations)      : {len(osm_codes):>4}')
    lines.append(f'  Présents dans les deux             : {len(in_both):>4}')
    lines.append(f'  Dans UrbIS mais absents d\'OSM      : {len(only_in_urbis):>4}')
    lines.append(f'  Dans OSM mais absents d\'UrbIS      : {len(only_in_osm):>4}')
    lines.append('')

    # -----------------------------------------------------------------------
    lines.append('CODES POSTAUX PRÉSENTS DANS LES DEUX SOURCES')
    lines.append('-' * 40)
    if in_both:
        for pc in in_both:
            d = osm_detail_map.get(pc, {})
            name_fr = d.get('name_fr') or d.get('name', '')
            name_nl = d.get('name_nl', '')
            addr_count = urbis_stats.get(pc, 0)
            name_str = ''
            if name_fr or name_nl:
                parts = [p for p in [name_fr, name_nl] if p]
                name_str = f'  [{" / ".join(parts)}]'
            osm_id = d.get('osm_id', '?')
            lines.append(
                f'  {pc}  osm_relation={osm_id:<10}  adresses_UrbIS={addr_count:>5}{name_str}'
            )
    else:
        lines.append('  (aucun)')
    lines.append('')

    # -----------------------------------------------------------------------
    lines.append('CODES POSTAUX DANS URBIS MAIS MANQUANTS DANS OSM')
    lines.append('(relation boundary=postal_code absente ou mal taguée)')
    lines.append('-' * 40)
    if only_in_urbis:
        for pc in only_in_urbis:
            addr_count = urbis_stats.get(pc, 0)
            lines.append(f'  {pc}  adresses_UrbIS={addr_count:>5}  → relation OSM à créer')
    else:
        lines.append('  (aucun — couverture OSM complète !)')
    lines.append('')

    # -----------------------------------------------------------------------
    lines.append('CODES POSTAUX DANS OSM MAIS ABSENTS D\'URBIS')
    lines.append('(relation présente dans OSM sans équivalent dans le GPKG UrbIS)')
    lines.append('-' * 40)
    if only_in_osm:
        for pc in only_in_osm:
            d = osm_detail_map.get(pc, {})
            name_fr = d.get('name_fr') or d.get('name', '')
            name_nl = d.get('name_nl', '')
            name_str = ''
            if name_fr or name_nl:
                parts = [p for p in [name_fr, name_nl] if p]
                name_str = f'  [{" / ".join(parts)}]'
            osm_id = d.get('osm_id', '?')
            lines.append(
                f'  {pc}  osm_relation={osm_id:<10}  → à vérifier (hors région ?){name_str}'
            )
    else:
        lines.append('  (aucun)')
    lines.append('')

    # -----------------------------------------------------------------------
    lines.append('DÉTAIL DES RELATIONS OSM TROUVÉES')
    lines.append('-' * 40)
    lines.append(f'  {"Code postal":<14} {"OSM relation ID":<16} {"Nom FR":<30} {"Nom NL"}')
    lines.append(f'  {"-"*12:<14} {"-"*14:<16} {"-"*28:<30} {"-"*28}')
    for d in sorted(osm_details, key=lambda x: x['postal_code']):
        pc = d['postal_code']
        osm_id = str(d['osm_id'])
        name_fr = (d.get('name_fr') or d.get('name', ''))[:28]
        name_nl = d.get('name_nl', '')[:28]
        lines.append(f'  {pc:<14} {osm_id:<16} {name_fr:<30} {name_nl}')
    lines.append('')

    lines.append('=' * 72)
    lines.append('FIN DU RAPPORT')
    lines.append('=' * 72)

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # 1. Trouver et télécharger le GPKG UrbIS si nécessaire
    existing_gpkg = glob.glob('*.gpkg')
    gpkg_path = None
    urbis_date = 'inconnue'

    if existing_gpkg:
        gpkg_path = existing_gpkg[0]
        print(f'[INFO] GPKG déjà présent : {gpkg_path}')
        # Essayer de lire la date depuis version.json
        if os.path.isfile('version.json'):
            with open('version.json') as f:
                vdata = json.load(f)
            urbis_date = vdata.get('urbis_date', 'inconnue')
    else:
        latest_dt, latest_url = find_latest_gpkg(FEED_URL)
        urbis_date = str(latest_dt.date())
        zip_name = os.path.basename(latest_url)
        if not os.path.isfile(zip_name):
            download(latest_url, zip_name)
        gpkg_path = extract_gpkg(zip_name)

    # 2. Télécharger le PBF OSM si nécessaire
    if not os.path.isfile(OSM_PBF_FILE):
        download(OSM_PBF_URL, OSM_PBF_FILE)
    else:
        print(f'[INFO] PBF déjà présent : {OSM_PBF_FILE}')

    # 3. Extraire les codes postaux
    urbis_codes, urbis_stats = load_urbis_postal_codes(gpkg_path)
    osm_codes, osm_details = load_osm_postal_codes(OSM_PBF_FILE)

    # 4. Générer le rapport
    report = build_report(
        urbis_codes=urbis_codes,
        urbis_stats=urbis_stats,
        osm_codes=osm_codes,
        osm_details=osm_details,
        urbis_date=urbis_date,
        osm_pbf_url=OSM_PBF_URL,
    )

    output_file = f'postal_code_report_{date.today().isoformat()}.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\n[OK] Rapport écrit : {output_file}')
    print(report)
