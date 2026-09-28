"""Configuration centrale du pipeline d'images produit.

La liste blanche des domaines et la classification des catégories ne sont
PAS dupliquées ici : elles sont lues dans scripts/verify_product_images.py,
qui reste la source de vérité unique (c'est ce fichier que le cycle
automatique RAOUIA_Boutique_PhotosAudit fait évoluer).
"""

import importlib.util
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

PRODUCTS_PATH = DATA_DIR / "products.json"
IMAGES_PATH = DATA_DIR / "product_images.json"
ATTEMPTED_PATH = DATA_DIR / "photos_audit_attempted.json"
REVIEW_QUEUE_PATH = DATA_DIR / "images_review_queue.json"

# Images optimisées servies par le site (chemin relatif au site).
OUTPUT_DIR = REPO_ROOT / "images" / "produits"
OUTPUT_WEB_PREFIX = "images/produits"

LOG_PATH = REPO_ROOT / "scripts" / "images_pipeline.log"

# --- Sortie ---------------------------------------------------------------
TARGET_SIZE = 800            # carré 800x800, produit centré, jamais recadré
OUTPUT_FORMAT = "webp"       # "webp" ou "jpg"
WEBP_QUALITY = 85
JPEG_QUALITY = 88

# --- Qualité minimale de l'image source -------------------------------------
MIN_SOURCE_WIDTH = 600
MIN_SOURCE_HEIGHT = 500
MIN_PRODUCT_PIXELS = 400      # taille réelle du produit (hors marges blanches)
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000  # protection "decompression bomb"

# Fond blanc/propre : part minimale de pixels quasi blancs sur la bordure,
# ou bordure très uniforme (fond propre non blanc, ex. gris clair studio).
BORDER_WHITE_RATIO_MIN = 0.85
BORDER_UNIFORM_STDDEV_MAX = 12.0

# --- Recherche --------------------------------------------------------------
EXCLUDED_TERMS = ["magasin", "boutique", "rayon", "étagère", "etagere", "vitrine", "stock"]
MAX_CANDIDATES_PER_PRODUCT = 20
MAX_REVIEW_CANDIDATES = 3

BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
GOOGLE_CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")

HTTP_USER_AGENT = "Mozilla/5.0 (compatible; RaouiaImagesBot/1.0; +https://www.raouia-informatique.ma)"
HTTP_TIMEOUT = 20


def _load_verifier():
    path = REPO_ROOT / "scripts" / "verify_product_images.py"
    spec = importlib.util.spec_from_file_location("verify_product_images", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_verifier = _load_verifier()
AUTHORIZED_DOMAINS = set(_verifier.AUTHORIZED_DOMAINS)
REJECTED_DOMAINS_HINTS = tuple(_verifier.REJECTED_DOMAINS_HINTS)
classify_category = _verifier.classify


def domain_authorized(domain: str) -> bool:
    domain = (domain or "").lower()
    return any(domain == d or domain.endswith("." + d) for d in AUTHORIZED_DOMAINS)
