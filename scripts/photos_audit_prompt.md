# Cycle de recherche de photos produit — instructions strictes

Tu opères dans `C:\Users\Administrateur.RAOUIAINFO\Documents\raouia-informatique`
(dépôt Git du site raouia-informatique). Ce cycle tourne automatiquement
toutes les 4h sans supervision humaine directe — applique donc ces règles
à la lettre, sans aucune tolérance.

## Périmètre de ce cycle

1. Lis `data/products.json` (catalogue) et `data/product_images.json`
   (état actuel des images/placeholders).
2. Lis `data/photos_audit_attempted.json` s'il existe (liste des
   références déjà tentées lors de cycles précédents — ne les retente
   pas, qu'elles aient réussi ou non, sauf si le fichier n'existe pas).
3. Sélectionne au maximum **20 références** parmi celles qui :
   - ont actuellement `"source": "placeholder"` dans product_images.json,
   - ne sont PAS dans `photos_audit_attempted.json`,
   - ont une désignation contenant une marque et un modèle identifiables
     sans ambiguïté (ex: "HP", "Canon", "Epson", "Logitech", "Hikvision",
     "TP-Link", "Samsung", "Lenovo", "Dell", "Toshiba", "Asus", "Kingston",
     "Seagate", "Brother", "Kyocera"...). Si la désignation est générique
     ou sans marque/modèle vérifiable (ex: "Agenda avec serrure",
     "SERVICE X", "PIECE DE CAISSE"), ignore-la complètement — ne
     cherche même pas d'image pour elle.
   - Marque SANS référence (ex. "PAPIER CANSON ROUGE A2", "CLASSEUR SICLA
     VERT") : autorisé, mais la source doit citer la marque ET chaque mot
     du nom (type d'objet, gamme) ET la couleur. Faute de saisie Sage
     connue : CONSON / CONSSON = Canson.
   - N'essaie plus de lire les pages d'Amazon, Cdiscount, Canon, Lenovo,
     Brother, Hikvision, Trodat et Dell : elles bloquent les robots.

## Articles SANS marque (photos d'illustration)

Ils ne relèvent PAS de ce cycle. Leur photo d'illustration du type
d'objet (`images/illustrations/`, `data/illustrations.json`) n'est
approuvée qu'après contrôle visuel (`images_produits.py illus ...`).
**Tu n'approuves jamais une illustration toi-même** et tu ne modifies
pas `data/illustrations.json`. Tu exécutes seulement l'étape
`illus apply` ci-dessous, qui applique celles déjà approuvées.

## Règles de recherche STRICTES (aucune exception)

1. **Requête = marque + référence exacte (SKU/EAN/code fabricant) + nom du
   produit.** Jamais la référence seule.
2. Exclure explicitement les résultats contenant : `magasin`, `boutique`,
   `rayon`, `étagère`, `vitrine`, `stock`.
3. Ne JAMAIS associer une image d'un produit similaire, équivalent, ou
   d'une autre marque/modèle — même proche. Un modèle différent, une
   couleur/capacité différente sans confirmation = rejet.
4. **Avant d'enregistrer** une image, vérifie que le titre de la page
   source ou le nom/URL du fichier contient explicitement la référence
   exacte ou le modèle précis du produit.
5. Photo de produit **isolé uniquement**, fond blanc/neutre de
   préférence. Rejet automatique : photo de magasin, de rayon,
   d'étagère, plusieurs articles en vrac, ou résolution < 600×500px.
6. Sources autorisées, dans cet ordre de préférence :
   - Fiche produit officielle du fabricant.
   - API/banque d'images officielle du fabricant.
   - Marketplace reconnue : Jumia, Amazon, Cdiscount (uniquement image
     de la fiche produit officielle du vendeur/marque, pas une photo
     tierce non vérifiable).
   - **Wikimedia Commons et toute autre banque d'images générique sont
     EXCLUS pour les articles de marque** (ils ne servent qu'aux
     illustrations validées à l'œil, voir plus haut) — incident du 08/08/2026 : des photos génériques
     Wikimedia avaient été appliquées par catégorie entière au lieu du
     produit exact, et une même photo avait été utilisée par erreur
     pour 3 téléphones Samsung différents. Ne reproduis jamais ça.
7. **Au moindre doute sur la correspondance à 100%, n'associe aucune
   photo.** Le produit garde son placeholder SVG de catégorie
   (`data/placeholders/<categorie>.svg` — catégories disponibles :
   toner, imprimante, ecran, clavier, souris, camera, reseau,
   ordinateur, stockage, audio, chargeur, batterie, cable, sac,
   papier, fourniture, nettoyage, divers, generique).

## Écriture des résultats

Pour chaque référence traitée avec succès, ajoute dans
`data/product_images.json` :
```json
"REF": {"image": "https://...", "source_page": "https://...", "source": "web"}
```
Ajoute TOUTES les références traitées ce cycle (trouvées ou non) à
`data/photos_audit_attempted.json` (simple liste JSON de refs), pour ne
jamais les re-tenter inutilement.

## Étapes finales OBLIGATOIRES (non négociables)

1. Exécute `python scripts/verify_product_images.py` — c'est un
   garde-fou déterministe qui revérifie mécaniquement chaque image
   "web" (domaine autorisé, dimensions réelles, correspondance
   référence/modèle) et repasse en placeholder tout ce qui ne passe
   pas. **Ne contourne jamais ce script et ne le désactive jamais.**
   Son verdict est final, même s'il contredit ton propre jugement.
2. Exécute `python scripts/images_produits.py localize` — re-valide
   chaque image "web" avec les règles strictes (marque, modèle ou
   référence constructeur, capacité, couleur, original/compatible, fond
   propre), la télécharge, l'optimise en WebP 800x800 dans
   `images/produits/` et met à jour les deux fichiers de données. Au
   moindre doute, l'image part en validation manuelle
   (`data/images_review_queue.json`) et le placeholder est conservé.
   Ne retraite jamais toi-même une référence présente dans cette file.
3. Exécute `python scripts/images_produits.py illus apply` (applique les
   illustrations déjà approuvées, ne remplace jamais une photo exacte).
4. Régénère `data/products.json` :
   `python -c "import sync_stock as m; m.write_products_json(m.fetch_products_from_sage())"`
5. `git add images/produits images/illustrations data/product_images.json data/products.json data/illustrations.json data/photos_audit_attempted.json data/images_review_queue.json`
   (les images DOIVENT être committées avec les fichiers de données qui
   les référencent, sinon le site affiche des images cassées).
6. Commit avec un message clair listant ce qui a été trouvé/écarté ce
   cycle.
7. `git push origin main`

Si aucune référence exploitable n'est trouvée ce cycle (toutes déjà
tentées, ou aucune ne passe la vérification), ne commite rien — c'est
un résultat normal et attendu, pas un échec.
