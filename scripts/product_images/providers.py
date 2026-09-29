"""Fournisseurs de candidats images.

Chaque fournisseur renvoie une liste de `Candidate` (URL image + page
source + titre). Il ne décide RIEN : toute la validation est faite ensuite
par matching.evaluate() puis imaging.check_quality().

Fournisseurs disponibles :
  - brave  : Brave Search API, recherche d'images (clé BRAVE_API_KEY)
  - google : Google Programmable Search / Custom Search JSON API
             (clés GOOGLE_CSE_KEY + GOOGLE_CSE_CX, recherche d'images activée)
  - file   : fichier JSON de candidats fournis à la main ou par un autre
             outil : [{"ref", "image_url", "page_url", "title"}, ...]
"""

import html
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from . import config
from .matching import Candidate, ProductProfile

log = logging.getLogger("product_images")


class ProviderError(Exception):
    pass


class BaseProvider:
    name = "base"

    def search(self, profile: ProductProfile) -> list[Candidate]:
        raise NotImplementedError


class BraveImageProvider(BaseProvider):
    name = "brave"
    URL = "https://api.search.brave.com/res/v1/images/search"

    def __init__(self, api_key: str = config.BRAVE_API_KEY):
        if not api_key:
            raise ProviderError("BRAVE_API_KEY non définie")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "X-Subscription-Token": api_key})

    def search(self, profile):
        resp = self.session.get(self.URL, timeout=config.HTTP_TIMEOUT, params={
            "q": profile.search_query(),
            "count": config.MAX_CANDIDATES_PER_PRODUCT,
            "safesearch": "strict",
        })
        if resp.status_code != 200:
            raise ProviderError(f"Brave HTTP {resp.status_code}: {resp.text[:200]}")
        return self.parse(resp.json())

    @staticmethod
    def parse(payload: dict) -> list[Candidate]:
        out = []
        for r in payload.get("results", []):
            props = r.get("properties") or {}
            image_url = props.get("url") or ""
            if not image_url:
                continue
            out.append(Candidate(
                image_url=image_url, page_url=r.get("url", ""), title=r.get("title", ""),
                provider="brave", width=props.get("width"), height=props.get("height")))
        return out


class GoogleCSEProvider(BaseProvider):
    name = "google"
    URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str = config.GOOGLE_CSE_KEY, cx: str = config.GOOGLE_CSE_CX):
        if not (api_key and cx):
            raise ProviderError("GOOGLE_CSE_KEY / GOOGLE_CSE_CX non définies")
        self.api_key, self.cx = api_key, cx

    def search(self, profile):
        resp = requests.get(self.URL, timeout=config.HTTP_TIMEOUT, params={
            "key": self.api_key, "cx": self.cx, "q": profile.search_query(),
            "searchType": "image", "num": 10, "safe": "active", "imgSize": "large",
        })
        if resp.status_code != 200:
            raise ProviderError(f"Google HTTP {resp.status_code}: {resp.text[:200]}")
        return self.parse(resp.json())

    @staticmethod
    def parse(payload: dict) -> list[Candidate]:
        out = []
        for it in payload.get("items", []):
            img = it.get("image") or {}
            out.append(Candidate(
                image_url=it.get("link", ""), page_url=img.get("contextLink", ""),
                title=it.get("title", ""), provider="google",
                width=img.get("width"), height=img.get("height")))
        return out


_META_IMAGE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::secure_url)?|twitter:image)["\'][^>]*>', re.I)
_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]*>', re.I)
_LD_IMAGE = re.compile(r'"image"\s*:\s*(?:\[\s*)?"(https?://[^"]+)"', re.I)


_ROBOTS: dict[str, RobotFileParser | None] = {}


def robots_allows(url: str) -> bool:
    """Respect du robots.txt de chaque site (ex. Jumia interdit sa recherche
    interne /catalog/?q= mais autorise les fiches produit)."""
    parts = urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _ROBOTS:
        rp = RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", timeout=config.HTTP_TIMEOUT,
                             headers={"User-Agent": config.HTTP_USER_AGENT})
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _ROBOTS[host] = rp
        except requests.RequestException:
            _ROBOTS[host] = None   # robots.txt injoignable : prudence, on s'abstient
    rp = _ROBOTS[host]
    return bool(rp) and rp.can_fetch("RaouiaImagesBot", url)


# Pages de liste/recherche (plusieurs produits) : leur image n'est pas celle
# d'UN produit précis (ex. jumia.ma/slp/..., /catalog/).
_LISTING_PAGE = re.compile(r"^/(slp|catalog|search|recherche|c)/|/mlp/|/mdp/", re.I)

_NOT_PRODUCT_IMAGE = re.compile(r"(logo|icon|favicon|placeholder|default|banner|sprite|badge|flag)", re.I)


def scan_page(page_url: str) -> tuple[str, list[str], str]:
    """Lit une page produit (domaine autorisé uniquement) et renvoie son titre,
    les URL d'images déclarées (og:image, twitter:image, JSON-LD) et l'URL
    finale (après redirection éventuelle)."""
    if not config.domain_authorized(urlparse(page_url).netloc):
        raise ProviderError(f"page hors liste blanche : {page_url}")
    if any(h in urlparse(page_url).netloc.lower() for h in config.BLOCKED_PAGE_HOSTS):
        raise ProviderError(f"site bloquant les robots, lecture abandonnée : {page_url}")
    if not robots_allows(page_url):
        raise ProviderError(f"lecture interdite par robots.txt : {page_url}")
    time.sleep(0.5)   # politesse : ~2 requêtes/s maximum
    resp = requests.get(page_url, timeout=config.HTTP_TIMEOUT,
                        headers={"User-Agent": config.HTTP_USER_AGENT,
                                 "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", ""):
        raise ProviderError(f"page {page_url} : HTTP {resp.status_code}")
    if not config.domain_authorized(urlparse(resp.url).netloc):
        raise ProviderError(f"redirection hors liste blanche : {resp.url}")
    text = resp.text[:2_000_000]
    title = ""
    m = _OG_TITLE.search(text)
    if m and _CONTENT.search(m.group(0)):
        title = _CONTENT.search(m.group(0)).group(1)
    elif _TITLE.search(text):
        title = _TITLE.search(text).group(1)
    urls = []
    for tag in _META_IMAGE.findall(text):
        c = _CONTENT.search(tag)
        if c:
            urls.append(urljoin(page_url, html.unescape(c.group(1))))
    urls += [html.unescape(u) for u in _LD_IMAGE.findall(text)]
    seen, out = set(), []
    for u in urls:
        if _NOT_PRODUCT_IMAGE.search(urlparse(u).path):
            continue   # logo/icône de site déclaré en og:image, pas le produit
        if u not in seen:
            seen.add(u)
            out.append(u)
    return html.unescape(re.sub(r"\s+", " ", title)).strip(), out[:5], resp.url


class FileProvider(BaseProvider):
    """Candidats pré-trouvés (manuellement ou par un autre outil).
    Chaque ligne donne soit `image_url` (+ page_url, title), soit seulement
    `page_url` : la page officielle est alors lue pour en extraire son titre
    et ses images déclarées (scraping ciblé, liste blanche obligatoire)."""
    name = "file"

    def __init__(self, path: Path):
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        self.rows: dict[str, list[dict]] = {}
        for r in rows:
            self.rows.setdefault(r["ref"], []).append(r)

    def search(self, profile):
        out = []
        for r in self.rows.get(profile.ref, []):
            if r.get("image_url"):
                out.append(Candidate(image_url=r["image_url"], page_url=r.get("page_url", ""),
                                     title=r.get("title", ""), provider="file"))
                continue
            if _LISTING_PAGE.search(urlparse(r["page_url"]).path):
                log.info("  [%s] page de liste ignorée (plusieurs produits) : %s", profile.ref, r["page_url"])
                continue
            try:
                title, images, final_url = scan_page(r["page_url"])
            except (ProviderError, requests.RequestException) as exc:
                log.info("  [%s] page ignorée : %s", profile.ref, exc)
                continue
            if not title:
                log.info("  [%s] page sans titre ignorée : %s", profile.ref, final_url)
                continue
            out += [Candidate(image_url=u, page_url=final_url, title=title, provider="page")
                    for u in images]
        return out


def build_providers(names: list[str], candidates_file: Path | None) -> list[BaseProvider]:
    providers = []
    for name in names:
        try:
            if name == "brave":
                providers.append(BraveImageProvider())
            elif name == "google":
                providers.append(GoogleCSEProvider())
            elif name == "file":
                if not candidates_file:
                    raise ProviderError("--candidates requis pour le fournisseur 'file'")
                providers.append(FileProvider(candidates_file))
            else:
                raise ProviderError(f"fournisseur inconnu : {name}")
        except ProviderError as exc:
            log.warning("Fournisseur '%s' désactivé : %s", name, exc)
    return providers
