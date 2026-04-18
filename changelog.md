# Changelog

## 2026-04-18

### Ajouté

- **Export OSM depuis le popup** - Chaque adresse affiche un bouton `⬇ .osm` qui génère un fichier XML prêt à être ouvert dans JOSM, contenant `addr:housenumber`, `addr:street` (bilingue FR - NL) et `ref:databrussels`.
- **INSPIRE ID cliquable** - L'identifiant dans le popup est un lien vers `databrussels.be/id/address/{id}` (nouvel onglet), avec un bouton de copie rapide dans le presse-papier.
- **Outil Lasso** - Bouton en haut à gauche de la carte permettant de dessiner un polygone de sélection (clic pour poser les points, double-clic ou clic droit pour terminer, Échap pour annuler). Les adresses contenues dans la zone sont comptées et exportables en un seul fichier `.osm`.


### Supprimé

- **Building ID** - Le champ `BU_ID` a été retiré du pipeline de génération des tuiles et du popup.

## 2026-02-25

- **Initial commit** - V0.1
