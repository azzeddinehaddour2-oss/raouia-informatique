#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_product_images.py
=========================
Garde-fou déterministe appliqué à data/product_images.json AVANT tout
commit/push. Ne fait confiance à aucune recherche (humaine, IA ou script) :
revérifie mécaniquement chaque entrée "web" et retombe sur le placeholder
SVG de catégorie au moindre doute.

Règles appliquées (voir docs/methodologie-recherche-images-produits.md) :
  - Source autorisée uniquement : domaine fabricant officiel connu, ou
    marketplace autorisée (Jumia / Amazon / Cdiscount).
  - Image réellement accessible (HTTP 200, Content-Type image/*).
  - Dimensions réelles >= LARGEUR_MIN x HAUTEUR_MIN.
  - Correspondance : la référence produit (ou un token significatif de sa
    désignation) doit apparaître dans l'URL de l'image OU dans
    source_page — sinon rejeté (évite la réutilisation d'une même image
    pour plusieurs produits différents, ex. incident Samsung A26/S25
    Ultra/S25 FE du 08/08/2026).

Usage :
    python scripts/verify_product_images.py [--dry-run]

Sans --dry-run, réécrit data/product_images.json en place et affiche un
résumé des entrées reverties.
"""

import io
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

try:
    from PIL import Image
except ImportError:
    Image = None

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES_PATH = REPO_ROOT / "data" / "product_images.json"
PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"

LARGEUR_MIN = 600
HAUTEUR_MIN = 500

AUTHORIZED_DOMAINS = {
    # Fabricants
    "hp.widen.net", "www.hp.com", "hp.com", "support.hp.com",
    "cdn.media.amplience.net", "www.canon-europe.com", "www.canon.com",
    "i8.amplience.net", "www.epson.eu", "www.epson.fr", "www.epson.com",
    "resource.logitech.com", "www.logitech.com",
    "assets.hikvision.com", "www.hikvision.com",
    "static.tp-link.com", "www.tp-link.com",
    "storage.toshiba.com", "www.toshiba.com",
    "images.samsung.com", "www.samsung.com",
    "p3-ofp.static.pub", "www.lenovo.com",
    "www.dell.com", "i.dell.com",
    "pisces.bbystatic.com",  # Best Buy CDN (fiches produit fabricant relayees)
    # Marketplaces autorisees
    "www.jumia.ma", "www.jumia.com.ng", "www.jumia.com",
    "images-na.ssl-images-amazon.com", "m.media-amazon.com",
    "www.amazon.com", "www.amazon.fr", "www.amazon.ma",
    "www.cdiscount.com", "i2.cdscdn.com",
}

REJECTED_DOMAINS_HINTS = ("wikimedia.org", "wikipedia.org", "pinterest", "google.com/imgres")

CATEGORY_RULES = [
    ("toner", [r"\bTONER\b", r"CARTOUCHE", r"\bENCRE\b", r"\bRIBBON\b", r"\bDRUM\b"]),
    ("imprimante", [r"IMPRIMANTE", r"\bSCANNER\b", r"\bMFP\b", r"COPIEUR", r"PHOTOCOPIEUR", r"PLASTIFIEUSE"]),
    ("ecran", [r"\bECRAN\b", r"MONITEUR", r"\bMONITOR\b"]),
    ("clavier", [r"CLAVIER", r"\bKEYBOARD\b"]),
    ("souris", [r"\bSOURIS\b", r"\bMOUSE\b"]),
    ("camera", [r"\bCAMERA\b", r"\bDVR\b", r"\bNVR\b", r"VIDEOSURVEILLANCE"]),
    ("reseau", [r"\bSWITCH\b", r"ROUTEUR", r"\bROUTER\b", r"\bWIFI\b", r"\bRESEAU\b", r"\bRJ ?45\b", r"\bMODEM\b", r"\bPOE\b", r"\bNAS\b"]),
    ("ordinateur", [r"PC PORTABLE", r"ORDINATEUR", r"\bLAPTOP\b", r"\bDESKTOP\b", r"\bNOTEBOOK\b", r"ELITEDESK", r"THINKPAD", r"LATITUDE", r"PRECISION", r"ELITEBOOK"]),
    ("stockage", [r"DISQUE DUR", r"\bSSD\b", r"CLE USB", r"CARTE SD", r"CARTE MEMOIRE", r"\bHDD\b"]),
    ("audio", [r"CASQUE", r"ECOUTEUR", r"HAUT.?PARLEUR", r"\bMICRO\b", r"ENCEINTE", r"\bSPEAKER\b"]),
    ("chargeur", [r"CHARGEUR", r"ADAPTATEUR", r"\bADAPTER\b", r"ALIMENTATION", r"\bPOWERBANK\b"]),
    ("batterie", [r"BATTERIE", r"\bPILE\b", r"\bPILES\b", r"\bACCUS?\b"]),
    ("cable", [r"\bCABLE\b", r"RALLONGE", r"\bHDMI\b", r"\bVGA\b"]),
    ("sac", [r"\bSAC\b", r"CARTABLE", r"SACOCHE"]),
    ("papier", [r"\bPAPIER\b", r"\bCAHIER\b", r"\bAGENDA\b", r"\bBLOC\b", r"REGISTRE", r"CLASSEUR", r"CHEMISE", r"ENVELOPPE", r"\bCARNET\b"]),
    ("fourniture", [r"\bSTYLO\b", r"MARQUEUR", r"AGRAFEUSE", r"\bAGRAFE\b", r"TROMBONE", r"CISEAUX", r"\bCOLLE\b", r"PUNAISE", r"CRAYON", r"\bGOMME\b", r"\bSCOTCH\b", r"CACHET", r"PERFORATRICE", r"SURLIGNEUR"]),
    ("nettoyage", [r"\bBALAI\b", r"SERPILLIERE", r"SERPILIERE", r"DETERGENT", r"NETTOYAGE", r"DESINFECTANT", r"EPONGE", r"MICROFIBRE", r"\bGANT\b"]),
]


def classify(designation: str) -> str:
    up = (designation or "").upper()
    for cat, patterns in CATEGORY_RULES:
        if any(re.search(pat, up) for pat in patterns):
            return cat
    return "divers"


def normalize_token(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def ref_matches_url(ref: str, designation: str, image_url: str, source_page: str) -> bool:
    """La référence (ou un token de la désignation, ex un modèle) doit
    apparaître dans l'URL image ou la page source — sinon on ne peut pas
    garantir que l'image correspond à CE produit précis."""
    haystack = normalize_token((image_url or "") + " " + (source_page or ""))
    ref_token = normalize_token(ref)
    if ref_token and len(ref_token) >= 3 and ref_token in haystack:
        return True
    # tokens alphanumériques de la désignation d'au moins 4 caractères
    # (ex. modèle "M171", "CF226A", "S731") - au moins un doit apparaître
    for word in re.findall(r"[A-Za-z0-9\-]{4,}", designation or ""):
        t = normalize_token(word)
        if len(t) >= 4 and t in haystack:
            return True
    return False


def check_image_live(url: str) -> tuple[bool, str]:
    """Vérifie HTTP 200 + Content-Type image + dimensions réelles."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 RaouiaVerifyBot/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "image" not in ctype:
                return False, f"content-type non image ({ctype})"
            data = resp.read(3_000_000)  # 3 Mo max, largement suffisant
    except Exception as exc:  # noqa: BLE001
        return False, f"erreur reseau ({exc})"

    if Image is None:
        return True, "PIL indisponible - dimensions non verifiees"

    try:
        with Image.open(io.BytesIO(data)) as img:
            w, h = img.size
    except Exception as exc:  # noqa: BLE001
        return False, f"image illisible ({exc})"

    if w < LARGEUR_MIN or h < HAUTEUR_MIN:
        return False, f"trop petite ({w}x{h})"
    return True, f"OK ({w}x{h})"


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    images = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
    products = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    designs = {p["ref"]: p["designation"] for p in products["products"]}

    reverted, kept, checked_live = [], [], 0

    for ref, info in images.items():
        if info.get("source") != "web":
            continue

        url = info.get("image", "")
        source_page = info.get("source_page") or ""
        domain = urlparse(url).netloc
        designation = designs.get(ref, "")

        reason = None
        if domain not in AUTHORIZED_DOMAINS or any(h in url for h in REJECTED_DOMAINS_HINTS):
            reason = f"domaine non autorise ({domain})"
        elif not ref_matches_url(ref, designation, url, source_page):
            reason = "reference/modele absent de l'URL et de source_page"
        else:
            checked_live += 1
            ok, detail = check_image_live(url)
            if not ok:
                reason = f"verification live echouee: {detail}"

        if reason:
            cat = classify(designation)
            reverted.append((ref, reason))
            if not dry_run:
                images[ref] = {
                    "image": f"data/placeholders/{cat}.svg",
                    "source_page": None,
                    "source": "placeholder",
                }
        else:
            kept.append(ref)

    print(f"Entrees 'web' revérifiées en direct : {checked_live}")
    print(f"Conservées (conformes) : {len(kept)}")
    print(f"Reverties (non conformes) : {len(reverted)}")
    for ref, reason in reverted:
        print(f"  - {ref}: {reason}")

    if not dry_run and reverted:
        IMAGES_PATH.write_text(
            json.dumps(images, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n{IMAGES_PATH} mis à jour.")
    elif dry_run:
        print("\n--dry-run : aucun fichier modifié.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
