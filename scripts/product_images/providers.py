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

import json
import logging
from pathlib import Path

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


class FileProvider(BaseProvider):
    """Candidats pré-trouvés (manuellement ou par un autre agent)."""
    name = "file"

    def __init__(self, path: Path):
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        self.by_ref: dict[str, list[Candidate]] = {}
        for r in rows:
            self.by_ref.setdefault(r["ref"], []).append(Candidate(
                image_url=r["image_url"], page_url=r.get("page_url", ""),
                title=r.get("title", ""), provider="file"))

    def search(self, profile):
        return list(self.by_ref.get(profile.ref, []))


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
