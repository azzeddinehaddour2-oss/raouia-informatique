# Pipeline d'images produit

Script : `scripts/images_produits.py` (package `scripts/product_images/`).
Règles de sourcing : `docs/methodologie-recherche-images-produits.md`.

## Installation

```bash
pip install -r requirements-images.txt   # requests, Pillow
```

Recherche automatique (facultatif, une seule clé suffit) :

| Fournisseur | Variables d'environnement | Obtenir la clé |
|---|---|---|
| Brave Search API (défaut) | `BRAVE_API_KEY` | https://api-dashboard.search.brave.com |
| Google Programmable Search | `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` | console Google Cloud + moteur avec recherche d'images activée |

Sous Windows (persistant) : `setx BRAVE_API_KEY "votre_cle"`, puis rouvrir le terminal.
Ne jamais écrire la clé dans un fichier du dépôt : il est public.

## Commandes

```bash
# Diagnostic : ce que le script comprend d'un produit, verdict sur une URL
python scripts/images_produits.py check HP-226A
python scripts/images_produits.py check HP-226A --url "https://..." --page "https://..." --title "..."

# Recherche pour les produits encore en placeholder (20 par défaut)
python scripts/images_produits.py search --limit 20 --dry-run
python scripts/images_produits.py search --providers brave,google --limit 50
python scripts/images_produits.py search --refs "HP-226A,G3410"
python scripts/images_produits.py search --providers file --candidates candidats.json

# Héberger localement les liens "web" existants (re-validation stricte)
python scripts/images_produits.py localize --dry-run
python scripts/images_produits.py localize

# Validation manuelle
python scripts/images_produits.py review list
python scripts/images_produits.py review html        # page visuelle scripts/images_review.html
python scripts/images_produits.py review approve REF 2   # candidat n°2
python scripts/images_produits.py review approve REF --url "https://..." --page "https://..."
python scripts/images_produits.py review reject REF
```

Une source produits CSV est acceptée (`--products fichier.csv`, colonnes `ref;designation`).
Format du fichier de candidats : `[{"ref": "...", "image_url": "...", "page_url": "...", "title": "..."}]`.

## Validation stricte (verdicts)

Pour chaque candidat, `matching.evaluate` rend :

- **ACCEPT** : source dans la liste blanche, marque confirmée, modèle principal (ou
  référence constructeur exacte, ex. `CF226A`) présent dans le titre/URL, aucune
  contradiction.
- **REVIEW** (validation manuelle, placeholder conservé, alerte dans le journal) :
  capacité non confirmée (stockage), couleur non confirmée (consommables), modèles
  voisins cités sur la même page, fond non blanc/propre, preuve insuffisante.
- **REJECT** : autre marque/modèle, autre capacité (ex. BX500 480 Go pour un 1 To),
  autre couleur, source décrivant un produit compatible, terme exclu (magasin, rayon...),
  domaine non autorisé.

Produits jamais traités automatiquement (placeholder + motif dans le journal) :
articles génériques sans marque, désignations à plusieurs marques, produits
compatibles/non originaux (NWC, COMP, WORD...) — une photo officielle serait trompeuse.

## Sorties

- Images : `images/produits/<ref-en-slug>.webp`, 800x800, produit centré sur fond
  blanc, jamais recadré (ex. `DS-3E1309P-EI/M` -> `ds-3e1309p-ei-m.webp`).
- `data/product_images.json` : `{"image": "images/produits/x.webp", "source": "local",
  "origin_url", "source_page", "validated": "auto"|"manuel", "validated_at"}`.
- `data/products.json` : champ `image` mis à jour immédiatement.
- `data/images_review_queue.json` : produits en attente de validation manuelle.
- `scripts/images_pipeline.log` : journal détaillé (alertes incluses).

Toujours committer `images/produits/` AVEC les fichiers `data/*.json` qui les
référencent, sinon le site affiche des images cassées.

## Tests

```bash
cd scripts && python -m unittest product_images.test_matching
```
