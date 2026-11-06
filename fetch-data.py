import argparse
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = 'PasLoin/Urbis-BeSt-Address-Brussels-compare-OSM'
TAG = 'data-latest'
FILES = ['addresses.pmtiles', 'search-index.json', 'version.json']
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; UrbIS-Sync/1.0)'}


def download(url, dest):
    tmp = dest.with_suffix(dest.suffix + '.part')
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as response, open(tmp, 'wb') as f:
        shutil.copyfileobj(response, f, 1024 * 1024)
    tmp.replace(dest)


def main():
    parser = argparse.ArgumentParser(description='Télécharge les données publiées dans la release data-latest.')
    parser.add_argument('--dir', default='data', help='dossier de destination')
    parser.add_argument('--repo', default=REPO, help='dépôt GitHub propriétaire/nom')
    parser.add_argument('--tag', default=TAG, help='tag de la release')
    args = parser.parse_args()
    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        url = f'https://github.com/{args.repo}/releases/download/{args.tag}/{name}'
        print(f'[DL] {url}', flush=True)
        try:
            download(url, target / name)
        except urllib.error.HTTPError as e:
            sys.exit(f'[ERREUR] {name} : HTTP {e.code}. La release {args.tag} existe-t-elle ? Lancer data.yml une fois.')
        size = (target / name).stat().st_size / 1024 / 1024
        print(f'[OK] {target / name} ({size:.1f} Mo)', flush=True)


if __name__ == '__main__':
    main()
