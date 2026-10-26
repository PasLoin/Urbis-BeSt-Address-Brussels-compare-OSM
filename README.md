# Urbis-BeSt-Address-Brussels-compare-OSM

A map of the official Brussels-Capital Region addresses (UrbIS/BeSt) compared with OpenStreetMap, to find addresses that are missing from OSM.

Live map: https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/

Address mapping in Brussels is best left to experienced mappers. Check the object history before you edit, and if you are unsure, verify on the ground or leave a note.

## Using the map

Each point is an UrbIS address drawn over the standard OSM basemap. Its popup links to Mapillary and Panoramax for imagery and to JOSM for editing, and shows the address INSPIRE ID with a link to databrussels.be. The JOSM link uses remote control on `127.0.0.1:8111`, so JOSM must be running with remote control enabled.

The filter panel shows or hides each status and gives coverage counts for the whole region. Only `missing` is shown at first, since that is usually the list worth working through. The search box looks up a street or an address either in the OSM data or through the UrbIS geocoder. You can export a single address from its popup, or every address inside a lasso selection, as an `.osm` file ready to open in JOSM.

## Address statuses

The map interface is in French. This table gives the label shown on the map for each status.

| Status | Map label | Meaning |
| --- | --- | --- |
| `ok` | Présente dans OSM | The address exists in OSM. |
| `missing` | Manquante dans OSM | The address is in UrbIS but not in OSM. |
| `verified_absent` | Vérifiée absente | A contributor checked on the ground and the address does not exist. |
| `missing_in_urbis` | Absente d'UrbIS (à vérifier) | The address is in OSM but not in UrbIS, and nobody has checked it yet. |
| `missing_in_urbis_verified` | Absente d'UrbIS (vérifiée) | The address is in OSM but not in UrbIS, and a contributor confirmed on the ground that it exists. |

## Matching

An UrbIS address matches OSM when `addr:street` and `addr:housenumber` agree, after both street names are normalized (accents removed, case folded).

The same street often has different names in the two sources. To handle this, the comparison builds an alias map from OSM highways and `associatedStreet` relations, using `name`, `alt_name`, `official_name`, `old_name`, `name:left`, `name:right` and their `fr`/`nl` variants. All the names found for one street are grouped, so an address matches whichever form UrbIS uses.

An address is `verified_absent` when OSM carries `not:addr:street` / `not:addr:housenumber`, or `was:addr:street` / `was:addr:housenumber` (usually on demolished buildings). An OSM-only address counts as verified when the `note` tag of the OSM object contains the word "urbis" (any case). OSM-only addresses outside the Brussels-Capital Region boundary (relation `54094`) are left out.

## Data updates

A GitHub Actions workflow runs every day. It downloads the latest UrbIS release and the OSM extract for Brussels, then rebuilds the vector tiles and the search index. The filter panel shows the date of each source.

Changes are listed in [changelog.md](changelog.md) (in French).

## License

The code in this repository is under the MIT license, see [LICENSE](LICENSE).

The data has its own licenses. OpenStreetMap data is © OpenStreetMap contributors and available under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). UrbIS data from the Brussels-Capital Region is released under [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

The generated files committed here are derived from OpenStreetMap and therefore fall under the ODbL, not the MIT license. `search-index.json` is built from the OSM extract. `addresses.pmtiles.gz` combines UrbIS addresses with a status computed from OSM data.
