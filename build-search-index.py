#!/usr/bin/env python3
"""
build-search-index.py
─────────────────────
Génère search-index.json depuis le PBF OSM Bruxelles.

Source : adresses présentes dans OpenStreetMap (addr:housenumber + addr:street),
         exactement les mêmes objets que ceux lus par AddressCollector dans
         compare-postal-codes-and-associetedStreet.py.

Usage :
  python3 build-search-index.py [chemin.pbf]
  python3 build-search-index.py   # utilise brussels_capital_region-latest.osm.pbf
"""

import sys, os, time, json, unicodedata
from collections import defaultdict
from shapely.geometry import Polygon, LineString
import osmium

OSM_PBF_FILE = 'brussels_capital_region-latest.osm.pbf'
OUTPUT_FILE  = 'search-index.json'


# ── Normalisation identique au srNorm() côté client ────────────────────────
def normalize(s):
    if not s:
        return ''
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.split())


# ── Collecteur OSM — même logique qu'AddressCollector dans le script compare ─
class AddressCollector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.addresses = []
        self.multi_count = 0

    def _process(self, tags, lat, lon):
        housenumber_raw = tags.get('addr:housenumber')
        street = tags.get('addr:street') or tags.get('addr:street_official')
        if not housenumber_raw or not street or lat is None or lon is None:
            return
        # Même traitement "4;6" → deux entrées séparées que dans le script compare
        housenumbers = [h.strip() for h in str(housenumber_raw).split(';') if h.strip()]
        for hn in housenumbers:
            self.addresses.append({'street': street, 'housenumber': hn,
                                   'lat': lat, 'lon': lon})
        if len(housenumbers) > 1:
            self.multi_count += 1

    def node(self, n):
        if n.location.valid():
            self._process(n.tags, n.location.lat, n.location.lon)

    def way(self, w):
        if not w.tags.get('addr:housenumber'):
            return
        try:
            coords = [(nd.location.lon, nd.location.lat)
                      for nd in w.nodes if nd.location.valid()]
            if len(coords) < 2:
                return
            geom = (Polygon(coords)
                    if coords[0] == coords[-1] and len(coords) >= 4
                    else LineString(coords))
            c = geom.centroid
            if not c.is_empty:
                self._process(w.tags, c.y, c.x)
        except Exception:
            pass


# ── Construction de l'index ────────────────────────────────────────────────
def build_index(pbf_path):
    print(f'[INDEX] Lecture de {pbf_path} …', flush=True)
    t0 = time.monotonic()

    h = AddressCollector()
    h.apply_file(pbf_path, locations=True)

    print(f'[INDEX] {len(h.addresses)} adresses OSM '
          f'({h.multi_count} issues d\'un housenumber multi) '
          f'en {time.monotonic()-t0:.1f}s', flush=True)

    street_list  = []   # labels affichés
    street_norms = []   # labels normalisés (fuzzy côté client)
    street_idx   = {}   # normalized → int index
    entries      = []   # [streetIdx, housenumber, lat, lon]

    for a in h.addresses:
        label = a['street']
        key   = normalize(label)
        if key not in street_idx:
            street_idx[key] = len(street_list)
            street_list.append(label)
            street_norms.append(key)
        entries.append([street_idx[key], a['housenumber'],
                        round(a['lat'], 6), round(a['lon'], 6)])

    print(f'[INDEX] {len(street_list)} rues uniques', flush=True)
    return {
        'v':  1,
        's':  street_list,
        'sn': street_norms,
        'a':  entries,
    }


if __name__ == '__main__':
    pbf = sys.argv[1] if len(sys.argv) > 1 else OSM_PBF_FILE
    if not os.path.isfile(pbf):
        sys.exit(f'[ERREUR] Fichier introuvable : {pbf}')
    index = build_index(pbf)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
    kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f'[OK] {OUTPUT_FILE} — {kb:.0f} KB', flush=True)
