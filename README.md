# Urbis-BeSt-Address-Brussels-compare-OSM

This tool overlays official Brussels-Capital Region addresses on a map and checks how they compare to what's already in OpenStreetMap.

## What's it for?

Spotting addresses that are missing from OSM, with quick visual context on an OSM basemap. Each point links directly to Mapillary, Panoramax, and JOSM to help with verification and editing.

## How it works

The basemap uses standard OSM raster tiles. Address data comes from a PMTiles vector layer, and each address gets a status assigned at generation time:

- `ok` — address exists in OSM
- `missing` — address not found in OSM
- `verified_absent` — a contributor has checked on the ground and confirmed the address doesn't physically exist

Use the filter panel to isolate the addresses you care about — typically `missing` is the most useful when looking for things to fix.

## Matching logic

OSM matching is based on `addr:street` and `addr:housenumber` tags. Verified absences use `not:addr:street` / `not:addr:housenumber`. Street names are normalized (accents stripped, case folded) before comparison. The JOSM link uses remote control on `127.0.0.1:8111`, so JOSM needs to be open with remote control enabled.

StreetName errors in official source is not yet implemented. 

## Use it : 

go to :  https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/

Address mapping in Brussels is best suited for experienced mappers. Always check the history and verify on the ground if you are unsure (or leave a note). Data is updated every Monday morning.
