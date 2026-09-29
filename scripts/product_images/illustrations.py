"""Bibliothèque de photos d'illustration pour les articles génériques.

Cycle :
  plan     -> clés de type nécessaires (ex. 'cable-hdmi') et articles concernés
  fetch    -> candidats libres de droits (Commons/Openverse), contrôles texte +
              qualité, planche contact pour la validation VISUELLE
  approve  -> un humain (ou l'audit visuel) choisit le candidat conforme
  apply    -> tous les articles purement génériques de ce type reçoivent
              l'illustration (source "illustration", jamais sur une photo exacte)

Rien n'est attribué sans validation visuelle : « correspond au type » se
vérifie à l'œil (couleur, forme), pas seulement par les mots-clés.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from . import catalog, config, imaging
from .generic_types import TYPES, classify_generic
from .libre import (FreeImage, commons_search, evidence_problems, libre_domain,
                    openverse_search)

log = logging.getLogger("product_images")

ILLUSTRATIONS_PATH = config.DATA_DIR / "illustrations.json"
ILLUSTRATIONS_DIR = config.REPO_ROOT / "images" / "illustrations"
ILLUSTRATIONS_WEB_PREFIX = "images/illustrations"
CANDIDATES_DIR = config.REPO_ROOT / "scripts" / "illustrations_candidates"

_RULES = {t.key: t for t in TYPES}
COLOUR_EN = {"noir": "black", "bleu": "blue", "bleu-ciel": "light blue", "bleu-fonce": "dark blue", "rouge": "red",
             "vert": "green", "jaune": "yellow", "orange": "orange", "rose": "pink", "violet": "purple",
             "blanc": "white", "gris": "grey", "marron": "brown", "bordeaux": "burgundy",
             "transparent": "transparent", "kraft": "kraft", "multicolore": "colored"}


def load() -> dict:
    return catalog.read_json(ILLUSTRATIONS_PATH, {})


def save(data: dict) -> None:
    catalog.write_json(ILLUSTRATIONS_PATH, data)


def split_key(key: str):
    """'chemise-cartonnee-bleu' -> (règle chemise-cartonnee, 'bleu')."""
    if key in _RULES:
        return _RULES[key], None
    for colour in sorted(COLOUR_EN, key=len, reverse=True):
        base = key[: -(len(colour) + 1)]
        if key.endswith("-" + colour) and base in _RULES:
            return _RULES[base], colour
    raise KeyError(key)


def plan() -> dict:
    """Clés nécessaires pour les articles sans vraie photo."""
    images = catalog.load_images()
    out: dict = {}
    for p in catalog.load_products():
        if images.get(p["ref"], {}).get("source") in ("local", "web"):
            continue
        g = classify_generic(p["designation"])
        if g.key:
            out.setdefault(g.key, {"label": g.rule.label, "refs": []})["refs"].append(p["ref"])
    return out


# --------------------------------------------------------------------------
# fetch : candidats + planche contact
# --------------------------------------------------------------------------

def _queries(rule, colour):
    for q in rule.queries:
        yield f"{COLOUR_EN[colour]} {q}" if colour else q
        yield f"{q} white background"


def fetch(keys: list[str], per_key: int = 6) -> Path | None:
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    tiles = []
    for key in keys:
        rule, colour = split_key(key)
        seen, kept = set(), []
        for q in _queries(rule, colour):
            if len(kept) >= per_key:
                break
            found: list[FreeImage] = []
            for search in (commons_search, openverse_search):
                try:
                    found += search(q)
                except Exception as exc:  # noqa: BLE001 - une banque en panne ne bloque pas l'autre
                    log.warning("[%s] %s en erreur : %s", key, search.__name__, exc)
            for fi in found:
                if len(kept) >= per_key or fi.url in seen:
                    continue
                seen.add(fi.url)
                problems = evidence_problems(fi, rule, colour)
                if problems:
                    log.debug("  [%s] écarté %s : %s", key, fi.title[:60], "; ".join(problems))
                    continue
                try:
                    img = imaging.download(fi.url, authorized=libre_domain)
                except imaging.ImageError as exc:
                    log.debug("  [%s] téléchargement refusé : %s", key, exc)
                    continue
                _, problems = imaging.check_quality(img)
                if problems:
                    log.debug("  [%s] qualité insuffisante %s : %s", key, fi.title[:60], "; ".join(problems))
                    continue
                n = len(kept) + 1
                dest = imaging.optimize_and_save(img, CANDIDATES_DIR / key / str(n), fmt="jpg")
                kept.append({**fi.__dict__, "file": str(dest.relative_to(config.REPO_ROOT)).replace("\\", "/")})
                tiles.append((f"{key} #{n}", dest))
        (CANDIDATES_DIR / key).mkdir(parents=True, exist_ok=True)
        (CANDIDATES_DIR / key / "candidates.json").write_text(
            json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("[%s] %d candidat(s) conforme(s) aux contrôles automatiques", key, len(kept))
    return contact_sheet(tiles, CANDIDATES_DIR / f"planche-{datetime.now():%Y%m%d-%H%M%S}.png") if tiles else None


def contact_sheet(tiles, dest: Path, size: int = 260, cols: int = 6) -> Path:
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * size, rows * (size + 22)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (label, path) in enumerate(tiles):
        with Image.open(path) as im:
            im.thumbnail((size - 8, size - 8))
            x, y = (i % cols) * size, (i // cols) * (size + 22)
            sheet.paste(im, (x + 4, y + 4))
            draw.rectangle([x + 2, y + 2, x + size - 2, y + size - 2], outline=(200, 200, 200))
            draw.text((x + 6, y + size + 4), label, fill=(0, 0, 0))
    sheet.save(dest)
    return dest


# --------------------------------------------------------------------------
# approve / revoke / apply
# --------------------------------------------------------------------------

def approve(key: str, n: int) -> str:
    rule, colour = split_key(key)
    cands = json.loads((CANDIDATES_DIR / key / "candidates.json").read_text(encoding="utf-8"))
    c = cands[n - 1]
    img = imaging.download(c["url"], authorized=libre_domain)
    dest = imaging.optimize_and_save(img, ILLUSTRATIONS_DIR / key)
    data = load()
    data[key] = {
        "image": f"{ILLUSTRATIONS_WEB_PREFIX}/{dest.name}",
        "label": rule.label + (f" ({colour.replace('-', ' ')})" if colour else ""),
        "origin_url": c["url"], "source_page": c["page_url"], "title": c["title"],
        "author": c["author"], "license": c["license"], "license_url": c["license_url"],
        "provider": c["provider"], "validated": "visuel", "validated_at": datetime.now().strftime("%Y-%m-%d"),
    }
    save(data)
    return data[key]["image"]


def revoke(key: str, reason: str) -> None:
    data = load()
    entry = data.pop(key, None)
    if not entry:
        raise ValueError(f"aucune illustration approuvée pour {key}")
    (config.REPO_ROOT / entry["image"]).unlink(missing_ok=True)
    save(data)
    log.warning("[%s] illustration retirée : %s", key, reason)
    apply()


def apply() -> dict:
    """Attribue les illustrations approuvées ; retire celles devenues
    invalides. Ne remplace JAMAIS une photo exacte (local/web)."""
    data = load()
    images = catalog.load_images()
    stats = {"attribuees": 0, "retirees": 0}
    for p in catalog.load_products():
        ref, current = p["ref"], images.get(p["ref"], {})
        if current.get("source") in ("local", "web"):
            continue
        g = classify_generic(p["designation"])
        entry = data.get(g.key) if g.key else None
        if entry:
            new = {"image": entry["image"], "source": "illustration", "type": g.key,
                   "label": entry["label"], "source_page": None}
            if current != new:
                images[ref] = new
                stats["attribuees"] += 1
        elif current.get("source") == "illustration":
            images[ref] = catalog.placeholder_entry(p["designation"])
            stats["retirees"] += 1
    catalog.save_images(images)
    catalog.sync_products_json(images)
    return stats
