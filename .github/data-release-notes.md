Données de la carte https://pasloin.github.io/Urbis-BeSt-Address-Brussels-compare-OSM/, mises à jour chaque jour. Les dates des sources UrbIS et OpenStreetMap sont dans `version.json`.

## Fichiers

| Fichier | Contenu | Licence |
| --- | --- | --- |
| `osm-absent-urbis.csv` | Adresses présentes dans OSM mais absentes d'UrbIS, une ligne par objet OSM et par numéro (UTF-8) | ODbL |
| `osm-absent-urbis.gpkg` | Les mêmes adresses en GeoPackage, couche `osm_absent_urbis`, EPSG:31370 | ODbL |
| `addresses.pmtiles` | Tuiles de la carte : adresses UrbIS avec leur statut calculé à partir d'OSM, et adresses présentes seulement dans OSM | ODbL |
| `search-index.json` | Index de recherche des rues et adresses OSM | ODbL |
| `version.json` | Dates des sources et compteurs par statut | ODbL |

## Licence

Ces fichiers sont dérivés d'OpenStreetMap et sont publiés sous l'[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Toute réutilisation doit mentionner « © les contributeurs d'OpenStreetMap » avec un lien vers https://www.openstreetmap.org/copyright, et une base de données dérivée qui est rendue publique doit rester sous ODbL.

Les adresses UrbIS de la Région de Bruxelles-Capitale sont publiées sous [CC0](https://creativecommons.org/publicdomain/zero/1.0/). Elles restent disponibles sous CC0 à leur source, https://datastore.brussels/. Dans `addresses.pmtiles`, elles portent un statut calculé à partir d'OSM, ce qui fait de l'ensemble une base dérivée d'OSM. Le CSV et le GeoPackage ne contiennent aucune donnée UrbIS : la comparaison avec UrbIS sert seulement à choisir quelles adresses OSM y figurent.

Le code du projet est sous licence MIT, voir [LICENSE](https://github.com/PasLoin/Urbis-BeSt-Address-Brussels-compare-OSM/blob/main/LICENSE).

---

Data behind the map, refreshed daily. All files are derived from OpenStreetMap and released under the ODbL 1.0: credit "© OpenStreetMap contributors" (https://www.openstreetmap.org/copyright). The UrbIS addresses are CC0 at their source. The code is MIT.
