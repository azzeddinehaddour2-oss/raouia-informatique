"""Lecture du catalogue, écriture atomique des fichiers de données, file de
validation manuelle et journal d'alertes."""

import csv
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from . import config

log = logging.getLogger("product_images")


def setup_logging(verbose: bool = False) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger("product_images")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    fh = logging.FileHandler(config.LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(fh)
    root.addHandler(sh)


# --------------------------------------------------------------------------
# Lecture/écriture JSON
# --------------------------------------------------------------------------

def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    """Écriture atomique : un crash ne laisse jamais un JSON à moitié écrit
    (ces fichiers sont servis en direct par le site)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_products(source: Path | None = None) -> list[dict]:
    """Produits {ref, designation, ...} depuis data/products.json (défaut) ou
    un CSV avec au moins les colonnes ref;designation (séparateur ; ou ,)."""
    source = source or config.PRODUCTS_PATH
    if source.suffix.lower() == ".csv":
        text = source.read_text(encoding="utf-8-sig")
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,")
        rows = csv.DictReader(text.splitlines(), dialect=dialect)
        return [{"ref": r["ref"].strip(), "designation": r["designation"].strip()}
                for r in rows if r.get("ref")]
    data = read_json(source, {})
    return data["products"] if isinstance(data, dict) else data


def load_images() -> dict:
    return read_json(config.IMAGES_PATH, {})


def save_images(images: dict) -> None:
    write_json(config.IMAGES_PATH, images)


def sync_products_json(images: dict) -> int:
    """Répercute les chemins d'image dans data/products.json (lu par
    index.html) sans attendre la prochaine synchro Sage 100.
    sync_stock.py refait exactement la même fusion à chaque passage."""
    data = read_json(config.PRODUCTS_PATH, None)
    if not isinstance(data, dict):
        return 0
    changed = 0
    for p in data.get("products", []):
        entry = images.get(p["ref"], {})
        new = entry.get("image")
        illus = entry.get("source") == "illustration"
        if new and (p.get("image") != new or bool(p.get("illustration")) != illus):
            p["image"] = new
            if illus:
                p["illustration"] = True
            else:
                p.pop("illustration", None)
            changed += 1
    if changed:
        write_json(config.PRODUCTS_PATH, data)
    return changed


# --------------------------------------------------------------------------
# Nommage des fichiers
# --------------------------------------------------------------------------

def slugify_ref(ref: str) -> str:
    """ex. 'DS-3E1309P-EI/M' -> 'ds-3e1309p-ei-m', 'NO.384556' -> 'no-384556'."""
    slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
    return slug or "ref"


def output_path_for(ref: str, all_refs) -> Path:
    """Chemin unique et stable. Si deux références donnent le même slug
    (ex. 'HP/TB' et 'HP-TB'), un suffixe court dérivé de la référence les
    distingue — le même fichier n'est jamais écrasé par un autre produit."""
    slug = slugify_ref(ref)
    if sum(1 for r in all_refs if slugify_ref(r) == slug) > 1:
        slug += "-" + hashlib.sha1(ref.encode("utf-8")).hexdigest()[:6]
    return config.OUTPUT_DIR / slug


def web_path(file_path: Path) -> str:
    return f"{config.OUTPUT_WEB_PREFIX}/{file_path.name}"


def placeholder_entry(designation: str) -> dict:
    cat = config.classify_category(designation)
    return {"image": f"data/placeholders/{cat}.svg", "source_page": None, "source": "placeholder"}


def local_entry(file_path: Path, origin_url: str, source_page: str, validated: str) -> dict:
    return {
        "image": web_path(file_path),
        "source": "local",
        "origin_url": origin_url,
        "source_page": source_page or None,
        "validated": validated,  # "auto" ou "manuel"
        "validated_at": datetime.now().strftime("%Y-%m-%d"),
    }


# --------------------------------------------------------------------------
# Tentatives & file de validation manuelle
# --------------------------------------------------------------------------

def load_attempted() -> set[str]:
    return set(read_json(config.ATTEMPTED_PATH, []))


def save_attempted(refs: set[str]) -> None:
    write_json(config.ATTEMPTED_PATH, sorted(refs))


def load_review_queue() -> dict:
    return read_json(config.REVIEW_QUEUE_PATH, {})


def save_review_queue(queue: dict) -> None:
    write_json(config.REVIEW_QUEUE_PATH, queue)
