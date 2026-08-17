# Méthodologie de recherche d'images produit

Règles strictes définies le 08/08/2026, à appliquer pour toute recherche
future d'images produit destinées à `data/product_images.json` (pilote
"Nos produits" / boutique en ligne raouia-informatique).

## 1. Ciblage de la recherche

- Requête = **marque + référence exacte + nom du produit** (jamais la
  référence seule : trop ambiguë sur un catalogue générique).
- Exclure explicitement les résultats contenant : `magasin`, `boutique`,
  `rayon`, `étagère`, `vitrine`, `stock` — ces termes signalent une photo
  de local ou de linéaire, pas un produit isolé.

## 2. Critères de qualité visuelle

- Uniquement des **photos de produit isolé**, de préférence sur fond blanc
  ou fond neutre.
- **Largeur minimale : 600 px** (vérifiée avant intégration, pas seulement
  déclarée par la source).
- Rejet systématique de toute image montrant un local, un rayon de
  magasin, ou plusieurs articles en vrac.

## 3. Sources autorisées

Par ordre de préférence :
1. Fiche produit officielle du fabricant (site constructeur).
2. APIs d'images produit / banques d'images officielles.
3. Marketplaces reconnues : Jumia, Amazon, Cdiscount — à condition que
   l'image provienne de la fiche produit (pas d'une photo vendeur tierce
   non vérifiable) et respecte les critères de qualité ci-dessus.

Toutes les images sont intégrées par **lien direct (hotlink)** — jamais
téléchargées ni ré-hébergées sur ce dépôt. Chaque entrée de
`product_images.json` conserve son `source_page` pour traçabilité.

## 4. Garde-fou (fallback)

Si aucune image nettoyée et isolée de bonne qualité n'est trouvée pour une
référence : **ne rien ajouter** dans `product_images.json` pour cette
référence. Le site retombe alors sur une **icône générique par catégorie**
(déterminée par mots-clés dans la désignation — voir `ICONES_CATEGORIES`
dans `boutique.html` / `index.html`), jamais sur une photo floue,
approximative ou hors-sujet.

## 5. Vérification avant intégration (obligatoire)

Avant tout commit, chaque URL candidate est vérifiée indépendamment
(hors de la recherche elle-même) :
- Requête HTTP réelle → code 200 et `Content-Type` de type image.
- Chargement effectif dans un navigateur (dimensions réelles ≥ 600 px de
  large).

Toute URL qui échoue l'une de ces vérifications est retirée, même si
l'agent de recherche l'avait initialement proposée.
