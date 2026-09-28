"""Téléchargement sécurisé, contrôle qualité et optimisation des images.

Sécurité :
  - seuls les domaines de la liste blanche sont contactés (y compris après
    redirection) ;
  - taille de téléchargement plafonnée, protection "decompression bomb" ;
  - l'image est décodée puis RÉ-ENCODÉE par Pillow : aucun octet du fichier
    d'origine n'est conservé (métadonnées et contenus parasites éliminés).
"""

import io
import statistics
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps

from . import config

Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS

_session = requests.Session()
_session.headers.update({"User-Agent": config.HTTP_USER_AGENT})


class ImageError(Exception):
    """Image refusée (réseau, format, taille, qualité)."""


@dataclass
class QualityReport:
    width: int
    height: int
    border_white_ratio: float
    border_stddev: float
    clean_corners: int = 0
    border_mean: float = 255.0

    @property
    def clean_background(self) -> bool:
        # Un produit qui remplit le cadre (écran, imprimante) touche les bords
        # mais laisse les coins blancs ; une photo de rayon/magasin a des coins
        # chargés. D'où le critère "au moins 2 coins blancs".
        return (self.border_white_ratio >= config.BORDER_WHITE_RATIO_MIN
                or (self.border_stddev <= config.BORDER_UNIFORM_STDDEV_MAX and self.border_mean >= 200)
                or self.clean_corners >= 2)
        # (une bordure uniforme mais sombre = bandes noires / fond noir : refusé)


def download(url: str) -> Image.Image:
    """Télécharge et décode une image depuis un domaine autorisé."""
    if not config.domain_authorized(urlparse(url).netloc):
        raise ImageError(f"domaine non autorisé : {urlparse(url).netloc}")
    try:
        resp = _session.get(url, timeout=config.HTTP_TIMEOUT, stream=True, allow_redirects=True)
    except requests.RequestException as exc:
        raise ImageError(f"erreur réseau : {exc}") from exc
    with resp:
        if resp.status_code != 200:
            raise ImageError(f"HTTP {resp.status_code}")
        final_domain = urlparse(resp.url).netloc
        if not config.domain_authorized(final_domain):
            raise ImageError(f"redirection vers un domaine non autorisé : {final_domain}")
        ctype = resp.headers.get("Content-Type", "")
        if "image" not in ctype:
            raise ImageError(f"le contenu n'est pas une image ({ctype})")
        buf = io.BytesIO()
        for chunk in resp.iter_content(64 * 1024):
            buf.write(chunk)
            if buf.tell() > config.MAX_DOWNLOAD_BYTES:
                raise ImageError("fichier trop volumineux")
    try:
        buf.seek(0)
        Image.open(buf).verify()          # intégrité
        buf.seek(0)
        img = Image.open(buf)
        img.load()
    except Exception as exc:  # noqa: BLE001 - Pillow lève des types variés
        raise ImageError(f"image illisible : {exc}") from exc
    return ImageOps.exif_transpose(img)


def flatten_on_white(img: Image.Image) -> Image.Image:
    """PNG transparents / palettes -> RGB sur fond blanc."""
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def quality_report(img: Image.Image) -> QualityReport:
    """Analyse la bordure (4 % de chaque côté) : un produit isolé sur fond
    blanc/propre a une bordure quasi blanche ou très uniforme ; une photo de
    magasin ou de rayon a une bordure chargée."""
    rgb = flatten_on_white(img)
    w, h = rgb.size
    small = rgb.resize((200, max(1, round(200 * h / w))))
    sw, sh = small.size
    band = max(2, round(min(sw, sh) * 0.04))
    px = small.load()
    border = [px[x, y] for y in range(sh) for x in range(sw)
              if x < band or y < band or x >= sw - band or y >= sh - band]
    white = sum(1 for r, g, b in border if r >= 235 and g >= 235 and b >= 235)
    lum = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in border]
    c = max(3, round(min(sw, sh) * 0.06))
    clean_corners = 0
    for x0, y0 in ((0, 0), (sw - c, 0), (0, sh - c), (sw - c, sh - c)):
        pts = [px[x, y] for y in range(y0, y0 + c) for x in range(x0, x0 + c)]
        if sum(1 for r, g, b in pts if min(r, g, b) >= 235) / len(pts) >= 0.9:
            clean_corners += 1
    return QualityReport(
        width=w, height=h,
        border_white_ratio=white / len(border),
        border_stddev=statistics.pstdev(lum),
        clean_corners=clean_corners,
        border_mean=statistics.fmean(lum),
    )


def check_quality(img: Image.Image) -> tuple[QualityReport, list[str]]:
    """Retourne le rapport + la liste des problèmes (vide = conforme)."""
    report = quality_report(img)
    problems = []
    if report.width < config.MIN_SOURCE_WIDTH or report.height < config.MIN_SOURCE_HEIGHT:
        problems.append(f"résolution insuffisante ({report.width}x{report.height})")
    ratio = max(report.width, report.height) / min(report.width, report.height)
    if ratio > 3:
        problems.append(f"proportions atypiques (bannière ? {report.width}x{report.height})")
    if not report.clean_background:
        problems.append(
            f"fond non blanc/propre (bordure blanche {report.border_white_ratio:.0%}, "
            f"{report.clean_corners}/4 coins blancs)")
    return report, problems


def optimize_and_save(img: Image.Image, dest: Path, fmt: str = config.OUTPUT_FORMAT) -> Path:
    """Produit centré dans un carré TARGET_SIZE sur fond blanc, sans
    recadrage ni agrandissement abusif, enregistré en WebP ou JPG optimisé."""
    rgb = flatten_on_white(img)
    # Retire les marges blanches excessives pour que le produit remplisse le
    # cadre de façon homogène d'une fiche à l'autre.
    bbox = ImageOps.invert(rgb).getbbox()
    if bbox:
        rgb = rgb.crop(bbox)
    size = config.TARGET_SIZE
    inner = round(size * 0.92)  # ~4 % de marge blanche de chaque côté
    rgb.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(rgb, ((size - rgb.width) // 2, (size - rgb.height) // 2))

    dest = dest.with_suffix("." + ("jpg" if fmt == "jpg" else "webp"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    if fmt == "jpg":
        canvas.save(tmp, "JPEG", quality=config.JPEG_QUALITY, optimize=True, progressive=True)
    else:
        canvas.save(tmp, "WEBP", quality=config.WEBP_QUALITY, method=6)
    tmp.replace(dest)
    return dest
