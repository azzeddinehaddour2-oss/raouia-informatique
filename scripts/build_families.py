#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regroupe les produits de data/products.json en familles de variantes
(couleur/déclinaison d'un même produit de base) et écrit le résultat
dans data/product_families.json.

Heuristique volontairement prudente : on ne groupe deux produits QUE si
- leur désignation, une fois les mots de couleur/variante finaux retirés,
  devient identique (et qu'un retrait a effectivement eu lieu), ET
- leurs références partagent un préfixe commun suffisamment long
  (>= 3 caractères) pour indiquer une vraie parenté (ex: "103-CY" / "103-M",
  "067BK" / "067CY").

Ré-exécutable après chaque synchronisation Sage 100 : il suffit de relancer
ce script pour régénérer data/product_families.json à partir du
data/products.json le plus récent.

Usage:
    python scripts/build_families.py
"""

import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_PATH = os.path.join(BASE_DIR, "data", "products.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "product_families.json")

# Mots de couleur / variante pouvant apparaître en fin de désignation.
# On retire une séquence de ces mots (dans n'importe quel ordre, ex.
# "NOIR WORD") du bout de la désignation pour obtenir le "nom de base".
COLOR_WORDS = {
    "CYAN": "Cyan",
    "MAGENTA": "Magenta",
    "YELLOW": "Yellow",
    "JAUNE": "Jaune",
    "NOIR": "Noir",
    "BLACK": "Black",
    "BLEU": "Bleu",
    "ROUGE": "Rouge",
    "VERT": "Vert",
    "BLANC": "Blanc",
    "WORD": "Word",
    "BK": "Black",
    "CY": "Cyan",
    "MG": "Magenta",
    "MT": "Magenta",
    "YL": "Yellow",
}

MIN_PREFIX_LEN = 3


def normalize_spaces(s):
    return re.sub(r"\s+", " ", s or "").strip()


def strip_trailing_variant_words(designation):
    """Retire la séquence de mots de couleur/variante en fin de désignation.

    Retourne (nom_de_base, liste_des_mots_retires_dans_l_ordre_original).
    """
    words = normalize_spaces(designation).split(" ")
    removed = []
    while words:
        last = words[-1].strip("/,.-").upper()
        if last in COLOR_WORDS:
            removed.insert(0, words.pop())
        else:
            break
    base = normalize_spaces(" ".join(words))
    return base, removed


def variant_label(removed_words):
    if not removed_words:
        return None
    labels = []
    for w in removed_words:
        key = w.strip("/,.-").upper()
        labels.append(COLOR_WORDS.get(key, w.strip("/,.-").title()))
    return " ".join(labels)


def common_prefix_len(a, b):
    n = 0
    for ca, cb in zip(a, b):
        if ca.upper() != cb.upper():
            break
        n += 1
    return n


def slugify(text):
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text or "famille"


def main():
    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    products = data.get("products", [])

    # Regroupement initial par nom de base (uniquement pour les produits
    # dont la désignation se termine par un mot de couleur/variante connu).
    groups = {}  # base_name -> list of (product, removed_words)
    for p in products:
        designation = p.get("designation") or ""
        base, removed = strip_trailing_variant_words(designation)
        if not removed or not base:
            continue  # pas de mot de couleur détecté en fin de nom -> produit simple
        groups.setdefault(base, []).append((p, removed))

    families = []
    for base_name, entries in groups.items():
        if len(entries) < 2:
            continue  # une seule variante détectée -> pas une vraie famille

        refs = [p.get("ref", "") for p, _ in entries]
        # Préfixe commun à TOUTES les références du groupe.
        prefix = refs[0]
        for r in refs[1:]:
            l = common_prefix_len(prefix, r)
            prefix = prefix[:l]
        if len(prefix) < MIN_PREFIX_LEN:
            continue  # préfixe de référence trop court -> probablement pas une vraie famille

        variants = []
        for p, removed in entries:
            variants.append({
                "ref": p.get("ref", ""),
                "variant_label": variant_label(removed) or "",
            })
        # Trie les variantes par référence pour un ordre stable.
        variants.sort(key=lambda v: v["ref"])

        family_id = slugify(base_name)
        families.append({
            "family_id": family_id,
            "base_name": base_name,
            "variants": variants,
        })

    # Dédoublonne les family_id éventuellement identiques.
    seen_ids = {}
    for fam in families:
        fid = fam["family_id"]
        seen_ids[fid] = seen_ids.get(fid, 0) + 1
        if seen_ids[fid] > 1:
            fam["family_id"] = "{}-{}".format(fid, seen_ids[fid])

    families.sort(key=lambda f: f["base_name"])

    output = families
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_variants = sum(len(f["variants"]) for f in families)
    avg = (total_variants / len(families)) if families else 0
    print("Familles créées : {}".format(len(families)))
    print("Variantes totales regroupées : {}".format(total_variants))
    print("Taille moyenne de famille : {:.2f} variantes".format(avg))


if __name__ == "__main__":
    main()
