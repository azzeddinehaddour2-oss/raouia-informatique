"""Banques d'images libres (sans clé API) pour les photos d'illustration des
articles génériques : Wikimedia Commons et Openverse.

Seules les licences qui autorisent l'usage commercial sont retenues
(CC0, domaine public, CC BY, CC BY-SA). L'auteur et la licence sont
conservés pour la page « Crédits photos » du site (obligation CC BY/BY-SA).

Aucun contournement : API publiques officielles, User-Agent identifié,
0,5 s entre deux requêtes.
"""

import html
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from . import config
from .matching import detect_brands, normalize_text

log = logging.getLogger("product_images")

LIBRE_DOMAINS = {"upload.wikimedia.org", "live.staticflickr.com", "farm1.staticflickr.com",
                 "farm2.staticflickr.com", "farm3.staticflickr.com", "farm4.staticflickr.com",
                 "farm5.staticflickr.com", "farm6.staticflickr.com", "farm8.staticflickr.com",
                 "farm9.staticflickr.com", "farm66.staticflickr.com", "cdn.stocksnap.io",
                 "images.rawpixel.com"}

OK_LICENSES = ("cc0", "pdm", "pd", "public domain", "cc by", "cc-by", "by", "by-sa", "cc by-sa", "cc-by-sa")
BAD_LICENSES = ("nc", "nd", "gfdl only", "fair use")


def libre_domain(domain: str) -> bool:
    domain = (domain or "").lower()
    return domain in LIBRE_DOMAINS


@dataclass
class FreeImage:
    url: str
    page_url: str
    title: str
    description: str
    license: str
    license_url: str
    author: str
    width: int
    height: int
    provider: str

    def evidence(self) -> str:
        return normalize_text(" ".join([self.title, self.description, urlparse(self.url).path]))


_session = requests.Session()
_session.headers.update({"User-Agent": config.HTTP_USER_AGENT})
_last = [0.0]


def _get(url, params):
    wait = 0.5 - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    r = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _license_ok(lic: str) -> bool:
    low = (lic or "").lower().replace("_", " ")
    if any(b in low.replace("-", " ").split() for b in ("nc", "nd")) or "non-commercial" in low:
        return False
    return any(ok in low for ok in OK_LICENSES)


def commons_search(query: str, limit: int = 30) -> list[FreeImage]:
    data = _get("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1200,
    })
    out = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not _license_ok(lic) or info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        out.append(FreeImage(
            url=info.get("thumburl") or info.get("url", ""),
            page_url=info.get("descriptionurl", ""),
            title=page.get("title", "").removeprefix("File:"),
            description=_strip_html(meta.get("ImageDescription", {}).get("value", ""))[:400]
                        + " " + meta.get("Categories", {}).get("value", "").replace("|", " "),
            license=lic, license_url=meta.get("LicenseUrl", {}).get("value", ""),
            author=_strip_html(meta.get("Artist", {}).get("value", ""))[:120] or "inconnu",
            width=info.get("width", 0), height=info.get("height", 0), provider="commons"))
    return out


def openverse_search(query: str, limit: int = 20) -> list[FreeImage]:
    data = _get("https://api.openverse.org/v1/images/", {
        "q": query, "license": "cc0,pdm,by,by-sa", "page_size": limit, "mature": "false"})
    out = []
    for r in data.get("results", []):
        lic = f"CC {r.get('license', '').upper()} {r.get('license_version') or ''}".strip()
        if r.get("license") in ("cc0", "pdm"):
            lic = "CC0" if r["license"] == "cc0" else "Domaine public"
        out.append(FreeImage(
            url=r.get("url", ""), page_url=r.get("foreign_landing_url", ""),
            title=r.get("title") or "", description=" ".join(t.get("name", "") for t in r.get("tags") or []),
            license=lic, license_url=r.get("license_url", ""), author=(r.get("creator") or "inconnu")[:120],
            width=r.get("width") or 0, height=r.get("height") or 0, provider="openverse"))
    return out


# Mots anglais/français attendus dans la source pour chaque couleur de clé.
COLOUR_EVIDENCE = {
    "noir": ["BLACK", "NOIR"], "bleu": ["BLUE", "BLEU"], "bleu-ciel": ["LIGHT BLUE", "SKY BLUE", "BLEU CIEL"],
    "bleu-fonce": ["DARK BLUE", "NAVY", "BLEU FONCE"], "rouge": ["RED", "ROUGE"], "vert": ["GREEN", "VERT"],
    "jaune": ["YELLOW", "JAUNE"], "orange": ["ORANGE"], "rose": ["PINK", "ROSE"], "violet": ["PURPLE", "VIOLET"],
    "blanc": ["WHITE", "BLANC"], "gris": ["GREY", "GRAY", "GRIS"], "marron": ["BROWN", "MARRON"],
    "bordeaux": ["BURGUNDY", "BORDEAUX"], "transparent": ["TRANSPARENT", "CLEAR"], "kraft": ["KRAFT", "BROWN"],
    "multicolore": ["COLORED", "COLOURED", "COLORFUL", "COLOURFUL", "ASSORTED", "MULTICOLOR", "COLOURS", "COLORS"],
}


def evidence_problems(img: FreeImage, rule, colour: str | None) -> list[str]:
    """Contrôle texte avant tout téléchargement : type d'objet et couleur
    cités par la source, aucune marque (une illustration doit être neutre)."""
    ev = img.evidence()
    problems = []
    if not any(all(w in ev for w in normalize_text(q).split()) for q in rule.queries):
        problems.append("type d'objet non cité par la source")
    if colour and not any(c in ev for c in COLOUR_EVIDENCE.get(colour, [colour.upper()])):
        problems.append(f"couleur '{colour}' non citée par la source")
    brands = detect_brands(ev)
    if brands:
        problems.append(f"marque visible probable ({', '.join(sorted(brands))})")
    if img.width and img.height and (img.width < config.MIN_SOURCE_WIDTH or img.height < config.MIN_SOURCE_HEIGHT):
        problems.append(f"résolution insuffisante ({img.width}x{img.height})")
    return problems
