# Urbis-BeSt-Address-Brussels-compare-OSM

A map of the official Brussels-Capital Region addresses (UrbIS/BeSt) compared with OpenStreetMap, to find addresses that are missing from OSM.

Live map, in French: https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/ and in English: https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/en/

Address mapping in Brussels is best left to experienced mappers. Check the object history before you edit, and if you are unsure, verify on the ground or leave a note.

## Using the map

Each point is an UrbIS address drawn over the standard OSM basemap. Its popup links to Mapillary and Panoramax for imagery and to JOSM for editing, and shows the address INSPIRE ID with a link to databrussels.be. The JOSM link uses remote control on `127.0.0.1:8111`, so JOSM must be running with remote control enabled.

The filter panel shows or hides each status and gives coverage counts for the whole region. Only `missing` is shown at first, since that is usually the list worth working through. The search box looks up a street or an address either in the OSM data or through the UrbIS geocoder. You can export a single address from its popup, or every address inside a lasso selection, as an `.osm` file ready to open in JOSM.

## Address statuses

The map is available in French and English. This table gives the label shown on the map for each status.

| Status | French label | English label | Meaning |
| --- | --- | --- | --- |
| `ok` | Présente dans OSM | Present in OSM | The address exists in OSM. |
| `missing` | Manquante dans OSM | Missing from OSM | The address is in UrbIS but not in OSM. |
| `verified_absent` | Vérifiée absente | Verified absent | A contributor checked on the ground and the address does not exist. |
| `missing_in_urbis` | Absente d'UrbIS (à vérifier) | Not in UrbIS (to check) | The address is in OSM but not in UrbIS, and nobody has checked it yet. |
| `missing_in_urbis_verified` | Absente d'UrbIS (vérifiée) | Not in UrbIS (verified) | The address is in OSM but not in UrbIS, and a contributor confirmed on the ground that it exists. |

## Matching

An UrbIS address matches OSM when `addr:street` and `addr:housenumber` agree, after both street names are normalized (accents removed, case folded).

The same street often has different names in the two sources. To handle this, the comparison builds an alias map from OSM highways and `associatedStreet` relations, using `name`, `alt_name`, `official_name`, `old_name`, `name:left`, `name:right` and their `fr`/`nl` variants. All the names found for one street are grouped, so an address matches whichever form UrbIS uses.

An address is `verified_absent` when OSM carries `not:addr:street` / `not:addr:housenumber`, or `was:addr:street` / `was:addr:housenumber` (usually on demolished buildings). An OSM-only address counts as verified when the `note` tag of the OSM object contains the word "urbis" (any case). OSM-only addresses outside the Brussels-Capital Region boundary (relation `54094`) are left out.

## Data updates

A GitHub Actions workflow runs every day. It downloads the latest UrbIS release and the OSM extract for Brussels, rebuilds the vector tiles and the search index, and publishes them in the `data-latest` release once they pass validation. The filter panel shows the date of each source.

Changes are listed in [changelog.md](changelog.md) (in French).

## Development

The page is built from the Jinja template `templates/index.html.j2` and ES modules in `js/`. The site published on GitHub Pages is generated into `_site/` by `build-site.py`, one page per language, and the data files come from the `data-latest` release, which the daily `data.yml` workflow updates once the data passes `tests/test_data.py`.

To run the site locally (Python 3.10 or later):

```sh
pip install -r requirements-dev.txt
python3 fetch-data.py
python3 build-site.py
python3 serve-local.py --dir _site
```

Then open `http://127.0.0.1:8000/`. `serve-local.py` supports the byte-range requests PMTiles needs.

Tests:

```sh
python3 check-i18n.py
npm test
python3 -m pytest tests/test_site.py tests/test_data.py
python3 -m playwright install chromium
python3 -m pytest tests/test_e2e.py
```

`npm test` needs Node.js 22 or later. The `site.yml` workflow runs all of these on every pull request and before each deployment.

## Translations

Every piece of interface text lives in `i18n/fr.json`, the reference, and has the same key in each other language file, such as `i18n/en.json`. `build-site.py` generates one page per language from `templates/index.html.j2` and inlines that page's dictionary, which the JavaScript reads through `t()` in `js/i18n.js`.

To add a text, add its key to every file in `i18n/`, then use `{{ t('my.key') }}` in the template or `t('my.key')` in the JavaScript. A key whose text depends on a number takes `one` and `other` forms, chosen by `Intl.PluralRules`. `check-i18n.py` fails if a key is missing in a language, if the `{variables}` differ between languages, or if French text is written directly in the template or the JavaScript.

## License

The code in this repository is under the MIT license, see [LICENSE](LICENSE).

The data has its own licenses. OpenStreetMap data is © OpenStreetMap contributors and available under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). UrbIS data from the Brussels-Capital Region is released under [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

The generated files published in the `data-latest` release are derived from OpenStreetMap and therefore fall under the ODbL, not the MIT license. `search-index.json` is built from the OSM extract. `addresses.pmtiles` combines UrbIS addresses with a status computed from OSM data.
