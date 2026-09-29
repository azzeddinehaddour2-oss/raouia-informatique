"""Sonde de pages trouvées par recherche web (validation manuelle assistée).

Pour chaque ligne {ref, page} d'un fichier JSON : lit la page (robots.txt
respecté, sites anti-robots ignorés), relève son titre et ses images
déclarées (og:image / JSON-LD), évalue la correspondance texte avec les
règles strictes, télécharge l'image, contrôle la qualité et produit une
planche contact. Rien n'est attribué ici : l'attribution passe par
`review approve REF --url IMG --page PAGE --trusted` après contrôle visuel.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from . import catalog, config, imaging
from .illustrations import contact_sheet
from .matching import Candidate, build_profile, evaluate
from .providers import _CONTENT, _LD_IMAGE, _META_IMAGE, _NOT_PRODUCT_IMAGE, _OG_TITLE, _TITLE, robots_allows

PROBE_DIR = config.REPO_ROOT / "scripts" / "illustrations_candidates" / "probe"


def read_page(url: str):
    host = urlparse(url).netloc.lower()
    if any(h in host for h in config.BLOCKED_PAGE_HOSTS):
        raise ValueError("site anti-robots ignoré")
    if not robots_allows(url):
        raise ValueError("interdit par robots.txt")
    time.sleep(0.5)
    r = requests.get(url, timeout=config.HTTP_TIMEOUT, headers={
        "User-Agent": config.HTTP_USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    if r.status_code != 200 or "html" not in r.headers.get("Content-Type", ""):
        raise ValueError(f"HTTP {r.status_code}")
    text = r.text[:2_000_000]
    import html as _html
    m = _OG_TITLE.search(text)
    title = _CONTENT.search(m.group(0)).group(1) if m and _CONTENT.search(m.group(0)) else (
        _TITLE.search(text).group(1) if _TITLE.search(text) else "")
    urls = [urljoin(r.url, _html.unescape(c.group(1))) for t in _META_IMAGE.findall(text)
            if (c := _CONTENT.search(t))]
    urls += [_html.unescape(u) for u in _LD_IMAGE.findall(text)]
    if not urls:
        # Boutiques sans og:image : on ne garde que les images dont le nom
        # de fichier reprend le nom du produit de la page (les pages listent
        # aussi des produits « similaires » qu'il ne faut surtout pas prendre).
        slug_words = set(re.findall(r"[a-z0-9]{3,}", (urlparse(r.url).path.rsplit("/", 1)[-1] + " " + title).lower()))
        for src in re.findall(r'(?:data-src|data-large_image|data-zoom-image|src|href)=["\']([^"\']+\.(?:jpe?g|png|webp))["\']', text, re.I):
            name_words = set(re.findall(r"[a-z0-9]{3,}", urlparse(src).path.lower()))
            if len(name_words & slug_words) >= 3:
                src = re.sub(r"-(?:medium|home|small|cart|listing|thumb)_default", "-large_default", src)
                src = re.sub(r"-\d{2,4}x\d{2,4}(\.\w+)$", r"\1", src)   # WooCommerce : taille d'origine
                urls.append(urljoin(r.url, _html.unescape(src)))
    out = []
    for u in urls:
        # "large_default" (PrestaShop) est une vraie photo produit : seul le
        # mot "default" isolé (image par défaut) est exclu.
        path = re.sub(r"(large|medium|home|thickbox|cart|small)_default", "", urlparse(u).path, flags=re.I)
        if u not in out and not _NOT_PRODUCT_IMAGE.search(path):
            out.append(u)
    return _html.unescape(re.sub(r"\s+", " ", title)).strip(), out[:3], r.url


def upscale(url: str) -> str:
    """Version haute résolution des vignettes de CDN courants (même image)."""
    url = re.sub(r"/fit-in/\d+x\d+/", "/fit-in/1000x1000/", url)                 # Bureau Vallée (cloudfront)
    url = re.sub(r"([?&])hei=\d+&wid=\d+", r"\1hei=1000&wid=1000", url)          # Raja (scene7)
    url = re.sub(r"/I_\d+/", "/WEB/", url)                                        # Alkor (Calipage, Burolike...)
    return url


def run(rows_path: Path) -> Path | None:
    rows = json.loads(Path(rows_path).read_text(encoding="utf-8"))
    products = {p["ref"]: p for p in catalog.load_products()}
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    tiles, report = [], []
    for row in rows:
        ref = row["ref"]
        prof = build_profile(ref, products.get(ref, {}).get("designation", ""))
        try:
            if row.get("image"):
                title, imgs, final = row.get("title", ""), [row["image"]], row.get("page", "")
            else:
                title, imgs, final = read_page(row["page"])
        except Exception as exc:  # noqa: BLE001
            report.append({"ref": ref, "page": row.get("page"), "erreur": str(exc)})
            continue
        imgs = list(dict.fromkeys(upscale(u) for u in imgs))
        if not imgs:
            report.append({"ref": ref, "page": final, "title": title, "erreur": "aucune image déclarée (og:image/JSON-LD)"})
        for k, u in enumerate(imgs[:2], 1):
            item = {"ref": ref, "designation": prof.designation, "title": title, "image": u, "page": final}
            if not prof.skip_reason:
                res = evaluate(prof, Candidate(u, final, title, provider="page"))
                item["texte"] = f"{res.verdict} ({'; '.join(res.reasons)[:160]})"
            else:
                item["texte"] = f"profil ignoré : {prof.skip_reason}"
            try:
                img = imaging.download(u, authorized=lambda d: True)
                _, problems = imaging.check_quality(img)
                item["qualite"] = "; ".join(problems) or "OK"
                dest = imaging.optimize_and_save(img, PROBE_DIR / f"{catalog.slugify_ref(ref)}-{k}", fmt="jpg")
                tiles.append((f"{ref} #{k}", dest))
                item["n"] = len(tiles)
            except imaging.ImageError as exc:
                item["qualite"] = f"téléchargement : {exc}"
            report.append(item)
    (PROBE_DIR / "rapport.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return contact_sheet(tiles, PROBE_DIR / "planche.png", size=240, cols=5) if tiles else None
