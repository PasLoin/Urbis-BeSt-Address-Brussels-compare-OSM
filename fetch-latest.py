#!/usr/bin/env python3
import sys
import os
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import json
from datetime import datetime, date, timedelta

FEED_URL = 'https://urbisdownload.datastore.brussels/atomfeed/2cf42541-1813-11ef-8a81-00090ffe0001-en.xml'
ATOM_NS  = 'http://www.w3.org/2005/Atom'
HEADERS  = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}

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
    with urllib.request.urlopen(req, timeout=120) as r:
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

def run(script, *args):
    cmd = [sys.executable, script] + list(args)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f'[ERREUR] {script} a échoué (code {result.returncode})')
        sys.exit(result.returncode)

if __name__ == '__main__':
    no_tiles = '--no-tiles' in sys.argv

    latest_dt, latest_url = find_latest_gpkg(FEED_URL)
    zip_name = os.path.basename(latest_url)

    if not os.path.isfile(zip_name):
        download(latest_url, zip_name)
    else:
        print(f'[DL] Déjà présent, téléchargement ignoré : {zip_name}')

    gpkg_path = extract_gpkg(zip_name)

    print(f'\n[TILES] Génération des PMTiles...')
    run('generate-tiles.py', gpkg_path, 'addresses.pmtiles')

    with open('version.json', 'w') as f:
        json.dump({
            'urbis_date': str(latest_dt.date()),
            'osm_date': str(date.today() - timedelta(days=1))
        }, f)
    print('[OK] version.json écrit.')

    print('\n[DONE] Pipeline complet.')
    print('       PMTiles : addresses.pmtiles')
