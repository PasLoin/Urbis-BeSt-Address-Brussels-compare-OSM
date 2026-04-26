# Changelog

## 2026-04-26

### Ajouté

- **Statistiques de couverture** - Le panneau de filtres affiche désormais le nombre total d'adresses UrbIS ainsi que la répartition par statut (présentes, manquantes, vérifiées absentes) avec pourcentages et barre de progression. Les compteurs sont calculés par le pipeline et enregistrés dans `version.json` (#9).
- **Panneau de filtres repliable** - Le panneau utilise un élément `<details>` natif, permettant de le replier d'un clic pour libérer de l'espace sur petit écran (#8).

## 2026-04-22

### Corrigé

- **Alias de rues pour `not:addr:*` / `was:addr:*`** - La vérification « vérifié absent » utilise désormais la liste étendue des variantes de noms de rues (incluant `official_name`, `alt_name`, etc.), comme c'est déjà le cas pour la détection `ok`. Corrige les faux « manquant » quand le nom OSM diffère du nom UrbIS (#6).

## 2026-04-19

### Ajouté

- **Support `was:addr:*`** - Les tags `was:addr:housenumber` / `was:addr:street` (utilisés sur les bâtiments démolis) sont désormais traités comme `not:addr:*`, marquant l'adresse comme « vérifiée absente » (#3).

## 2026-04-18

### Ajouté

- **Export OSM depuis le popup** - Chaque adresse affiche un bouton `⬇ .osm` qui génère un fichier XML prêt à être ouvert dans JOSM, contenant `addr:housenumber`, `addr:street` (bilingue FR - NL) et `ref:databrussels`.
- **INSPIRE ID cliquable** - L'identifiant dans le popup est un lien vers `databrussels.be/id/address/{id}` (nouvel onglet), avec un bouton de copie rapide dans le presse-papier.
- **Outil Lasso** - Bouton en haut à gauche de la carte permettant de dessiner un polygone de sélection (clic pour poser les points, double-clic ou clic droit pour terminer, Échap pour annuler). Les adresses contenues dans la zone sont comptées et exportables en un seul fichier `.osm`.


### Supprimé

- **Building ID** - Le champ `BU_ID` a été retiré du pipeline de génération des tuiles et du popup.

## 2026-02-25

- **Initial commit** - V0.1
