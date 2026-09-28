"""Validation stricte "correspondance 100 %" entre un produit et une image.

Principe : on ne cherche pas à reconnaître l'image (pas de vision), on
exige que les MÉTADONNÉES de la source (titre, URL de la page, URL de
l'image) prouvent qu'il s'agit du même produit exact. Au moindre doute,
le verdict est REVIEW (validation manuelle) ou REJECT — jamais ACCEPT.

Trois niveaux de verdict par candidat :
  ACCEPT : marque + modèle principal confirmés, aucune contradiction
           (capacité, couleur, original/compatible), source autorisée.
  REVIEW : plausible mais non prouvé (capacité ou couleur non mentionnée,
           plusieurs modèles voisins sur la même page, fond non blanc...).
  REJECT : contradiction explicite ou source interdite.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from . import config

ACCEPT, REVIEW, REJECT = "accept", "review", "reject"

# Marques reconnues -> alias (formes écrites possibles). Une désignation sans
# marque reconnue est considérée générique : pas de recherche d'image.
BRANDS = {
    "HP": ["HP", "HEWLETT PACKARD"],
    "CANON": ["CANON"],
    "EPSON": ["EPSON"],
    "LOGITECH": ["LOGITECH"],
    "HIKVISION": ["HIKVISION"],
    "HIKSEMI": ["HIKSEMI"],
    "TP-LINK": ["TP-LINK", "TPLINK"],
    "SAMSUNG": ["SAMSUNG"],
    "LENOVO": ["LENOVO"],
    "DELL": ["DELL"],
    "TOSHIBA": ["TOSHIBA"],
    "ASUS": ["ASUS"],
    "ACER": ["ACER"],
    "BROTHER": ["BROTHER"],
    "KYOCERA": ["KYOCERA"],
    "KINGSTON": ["KINGSTON"],
    "SEAGATE": ["SEAGATE"],
    "WESTERN DIGITAL": ["WESTERN DIGITAL"],  # "WD" seul trop ambigu (ex. WD-G2 pistolet colle)
    "SANDISK": ["SANDISK"],
    "CRUCIAL": ["CRUCIAL"],
    "LEXAR": ["LEXAR"],
    "HUAWEI": ["HUAWEI"],
    "XIAOMI": ["XIAOMI", "REDMI"],
    "APPLE": ["APPLE"],  # "iPhone" seul = souvent un accessoire tiers compatible
    "SONY": ["SONY"],
    "TENDA": ["TENDA"],
    "MERCUSYS": ["MERCUSYS"],
    "D-LINK": ["D-LINK", "DLINK"],
    "NETGEAR": ["NETGEAR"],
    "JBL": ["JBL"],
    "RICOH": ["RICOH"],
    "MICROSOFT": ["MICROSOFT"],
    "UGREEN": ["UGREEN"],
    "APC": ["APC"],
    "EATON": ["EATON"],
    "ZKTECO": ["ZKTECO"],
    "INGELEC": ["INGELEC"],
    "ALCATEL": ["ALCATEL"],
    "PHILIPS": ["PHILIPS"],
    "SYNOLOGY": ["SYNOLOGY"],
    "TRANSCEND": ["TRANSCEND"],
    "MIKROTIK": ["MIKROTIK"],
    "UBIQUITI": ["UBIQUITI"],
    "HONEYWELL": ["HONEYWELL"],
    "ZEBRA": ["ZEBRA"],
    "SHURE": ["SHURE"],
    "CASIO": ["CASIO"],
    "BIC": ["BIC"],
    "PILOT": ["PILOT"],
    "FABER-CASTELL": ["FABER-CASTELL", "FABER CASTELL"],
    "MAPED": ["MAPED"],
    "STABILO": ["STABILO"],
    "KANGARO": ["KANGARO"],
    "TRODAT": ["TRODAT"],
    "UHU": ["UHU"],
}

# Produit non original (compatible, recond., import parallèle) : une photo
# officielle du fabricant serait trompeuse -> jamais d'image automatique.
NON_ORIGINAL_MARKERS = re.compile(
    r"\b(NWC|COMP|COMPATIBLES?|WORD|CARRERA|IMPORTER|GENERIQUE|GENERIC|"
    r"ADAPTABLE|REMANUFACTURE[DS]?|RECONDITIONNE|REFURBISHED|COPIE|DIAMOND)\b"
)
CANDIDATE_NON_ORIGINAL = re.compile(
    r"\b(COMPATIBLES?|REMANUFACTURED?|GENERIC|GENERIQUE|REFURBISHED|RECONDITIONNE|ALTERNATIVE)\b"
    r"|\bREPLACEMENT FOR\b|\bREMPLACEMENT POUR\b|\bEN REMPLACEMENT\b"
)  # "Printhead Replacement Kit" (HP officiel) n'est PAS un indice de compatible

# Tokens techniques qui ne sont PAS un numéro de modèle.
SPEC_TOKEN = re.compile(
    r"^("
    r"\d+([.,]\d+)?(GB|GO|TB|TO|MB|MO|G|T|V|MAH|MHZ|GHZ|HZ|CM|MM|M|KG|ML|L|P|PX|MP|FPS)"
    r"|\d+[.,]\d+A|\dA"          # ampérage : 4.62A, 2A (mais 12A, 26A, 05A = modèles toner)
    r"|\d+(SSD|HDD|NVME|EMMC)"
    r"|I[3579]|R[3579]|\d{3,5}[UHKPX]{1,2}"
    r"|\d[GKU]|(USB|DDR|PCIE|SATA|GEN|CAT|RJ|WPA|HDMI|WIFI)\d.*"
    r"|\d+(MBPS|GBPS|PORTS?|VA|TH|ND|RD|ST|EME)"
    r"|\d+[.,]\d+"
    r"|(AC|AX|AV)\d{3,5}"
    r"|A[0-6]"                    # formats papier A4, A3
    r"|\d+(MA|GEN|DPI|PPM|IPM|RPM|RAM|CH|BIT|KHZ|MR)"  # mA, génération CPU, RAM, canaux...
    r"|\d+X\d+|M\.?2|W1[01][A-Z]*|QC\d.*|ADSL\d?|NVME\d?"
    r"|WIN\d+[A-Z]*|\d+PRO|\d+(ST|ND|RD|TH)GEN"   # Windows 11 Pro, génération CPU
    r"|20[12]\d"
    r")$"
)

COLOURS = {
    "black": ["NOIR", "BLACK", "BK", "BLK"],
    "cyan": ["CYAN", "BLEU", "BLUE"],
    "magenta": ["MAGENTA", "ROUGE", "RED"],
    "yellow": ["JAUNE", "YELLOW"],
    "white": ["BLANC", "WHITE"],
    "grey": ["GRIS", "GREY", "GRAY", "SILVER", "ARGENT"],
    "tricolor": ["COULEUR", "TRICOLOR", "TRICOLOUR", "TRI-COLOR", "TRI-COLOUR"],
}

# Génération du modèle (ThinkPad L13 Gen 2, ProBook 460 G11) - pas la
# génération du processeur ("i5 12TH GEN", "11Gen" sont exclus).
GENERATION = re.compile(r"(?<![0-9])(?:GEN(?:ERATION)?\s?(\d{1,2})(?!\s*(?:RAM|GO|GB|TH|ST|ND|RD|\d))|\bG(\d{1,2})I?\b)")


def extract_generations(text: str) -> set[str]:
    return {a or b for a, b in GENERATION.findall(normalize_text(text))}


CAPACITY = re.compile(r"(?<![A-Z0-9.,])(\d+(?:[.,]\d+)?)\s*(TB|TO|GB|GO|MB|MO)(?![A-Z])")

PACK_WORDS = re.compile(
    r"\b(PACK|LOT|KIT|MULTIPACK|DUO|TRIO|BUNDLE|COMBO)\b|\d\s*-?\s*PACK|\bBOITE DE\b|\bBOITE \d+"
    r"|\b\d+\s*(BOUTEILLES|CARTOUCHES|TONERS|STYLOS|MARQUEURS|FEUTRES|CRAYONS|SURLIGNEURS)\b")

# Papeterie : l'article et sa recharge partagent le même numéro (cachet
# Trodat 4912 / tampon encreur 4912, stylo / recharge G-2).
STATIONERY = re.compile(r"\b(CACHET|TAMPON|STYLO|MARQUEUR|FEUTRE|SURLIGNEUR|DATEUR)S?\b")
REFILL = re.compile(r"\b(ENCRE|ENCREUR|RECHARGES?|REFILLS?|INK PAD|CARTOUCHE)\b")


def _is_pack_title(raw: str) -> bool:
    up = unicodedata.normalize("NFKD", raw or "").encode("ascii", "ignore").decode().upper()
    return bool(PACK_WORDS.search(up)) or " + " in up or "+" in up.replace("C+", "")


MARKETPLACE_HINTS = ("amazon", "jumia", "cdiscount", "bbystatic", "cdscdn")


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def normalize_text(s: str) -> str:
    """Majuscules, sans accents, séparateurs d'URL remplacés par des espaces."""
    s = unquote(s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.upper()
    return re.sub(r"[/_?=&+%#|()\[\]{}\"'<>:;!*]", " ", s)


def tokenize(s: str) -> list[str]:
    return re.findall(r"[A-Z0-9]+(?:[.,]\d+[A-Z]*)?", normalize_text(s))


def compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(s))


def _alias_regex(alias: str) -> re.Pattern:
    parts = re.split(r"[\s\-]+", alias.upper())
    body = r"[\s\-_.]?".join(re.escape(p) for p in parts)
    return re.compile(r"(?<![A-Z0-9])" + body + r"(?![A-Z0-9])")


_BRAND_PATTERNS = {b: [_alias_regex(a) for a in aliases] for b, aliases in BRANDS.items()}


def detect_brands(text: str) -> set[str]:
    t = normalize_text(text)
    return {b for b, pats in _BRAND_PATTERNS.items() if any(p.search(t) for p in pats)}


CAPACITY_G = re.compile(r"(?<![A-Z0-9.,])(\d+)G(?![A-Z0-9])")


def extract_capacities_gb(text: str) -> set[float]:
    out = {float(n) for n in CAPACITY_G.findall(normalize_text(text)) if int(n) >= 8}
    for num, unit in CAPACITY.findall(normalize_text(text)):
        if unit in ("MB", "MO"):   # cache/tampon (ex. "256MB cache"), pas une capacité
            continue
        value = float(num.replace(",", "."))
        factor = {"TB": 1000, "TO": 1000, "GB": 1, "GO": 1, "MB": 0.001, "MO": 0.001}[unit]
        out.add(round(value * factor, 3))
    return out


def extract_colours(text: str, include_tricolor: bool, glued: bool = False) -> set[str]:
    """glued=True (désignations Sage) : détecte aussi une couleur collée à un
    autre mot, ex. 'TITANIUMBLACK', 'GRAPHITE6.4'."""
    words = set(tokenize(text)) | set(re.findall(r"TRI-COLOU?R", normalize_text(text)))
    flat = compact(text)
    found = set()
    for canon, variants in COLOURS.items():
        if canon == "tricolor" and not include_tricolor:
            continue
        if any(v in words for v in variants) or (glued and any(len(v) >= 5 and v in flat for v in variants)):
            found.add(canon)
    return found


# Puissance en watts : spécification pour les chargeurs/batteries/audio
# (65W, 90W), mais modèle ailleurs (imprimante HP Laser 107W).
WATT_SPEC_CATEGORIES = {"chargeur", "batterie", "audio"}
CPU_GPU_WORDS = {"RTX", "GTX", "RX", "CORE", "RYZEN", "ULTRA", "I3", "I5", "I7", "I9", "CELERON", "PENTIUM", "XEON"}
UNIT_WORDS = {"SSD", "HDD", "NVME", "RAM", "DDR4", "DDR5", "EMMC", "GB", "GO", "TB", "TO", "MB", "MO", "W", "V", "A", "MAH", "ML", "CM", "MM",
              "INCH", "POUCES", "POUCE", "PAGES", "PORTS", "PORT", "MBPS", "VA", "HZ", "MP"}


def model_tokens(designation: str, category: str = "") -> list[str]:
    """Numéros de modèle probables, dans l'ordre de la désignation."""
    tokens = []
    all_toks = tokenize(designation)
    for i, tok in enumerate(all_toks):
        nxt = all_toks[i + 1] if i + 1 < len(all_toks) else ""
        prv = all_toks[i - 1] if i > 0 else ""
        if tok.isdigit() and nxt in UNIT_WORDS:
            continue
        if tok.isdigit() and prv in CPU_GPU_WORDS:   # RTX 4050, Core 7, Ryzen 5 (pas 'i5 840G6')
            continue
        if not re.search(r"\d", tok):
            continue
        if SPEC_TOKEN.match(tok):
            continue
        if category in WATT_SPEC_CATEGORIES and re.fullmatch(r"\d+([.,]\d+)?W", tok):
            continue
        pure_digits = tok.isdigit()
        if (pure_digits and len(tok) < 3) or len(tok) < 2:
            continue
        if tok not in tokens:
            tokens.append(tok)
    return tokens


def o_to_zero(tok: str) -> str:
    """Saisie Sage fréquente : lettre O à la place du zéro dans un code
    modèle (DS-2CE16HOT pour DS-2CE16H0T). Appliqué seulement aux tokens
    contenant déjà un chiffre."""
    return tok.replace("O", "0") if re.search(r"\d", tok) else tok


def _candidate_token_set(text: str) -> set[str]:
    """Tokens + concaténations de 2-3 tokens consécutifs
    (ex. 'elitebook-840-g6' doit reconnaître le modèle '840G6')."""
    toks = [re.sub(r"[.,]", "", t) for t in tokenize(text)]
    out = set(toks)
    for n in (2, 3):
        for i in range(len(toks) - n + 1):
            out.add("".join(toks[i:i + n]))
    return out | {o_to_zero(t) for t in out}


# --------------------------------------------------------------------------
# Profil produit
# --------------------------------------------------------------------------

@dataclass
class ProductProfile:
    ref: str
    designation: str
    category: str
    brand: str | None = None
    models: list[str] = field(default_factory=list)
    capacities: set = field(default_factory=set)
    colours: set = field(default_factory=set)
    skip_reason: str | None = None

    @property
    def primary_model(self) -> str | None:
        longs = [m for m in self.models if len(m) >= 3]
        return (longs or self.models or [None])[0]

    @property
    def strong_tokens(self) -> list[str]:
        """Références constructeur très spécifiques (ex. CF226A, W2030A,
        P2722H) : leur présence prouve le produit même si le nom commercial
        (ex. '415A') n'apparaît pas dans la source."""
        return [m for m in self.models if len(m) >= 5 and re.search(r"[A-Z]", m)]

    def search_query(self) -> str:
        """marque + modèle principal + désignation nettoyée, termes exclus
        en négatif."""
        cleaned = re.sub(r"\s+", " ", self.designation).strip()
        excluded = " ".join(f"-{t}" for t in config.EXCLUDED_TERMS)
        return f'{self.brand} "{self.primary_model}" {cleaned} {excluded}'


def build_profile(ref: str, designation: str) -> ProductProfile:
    category = config.classify_category(designation)
    p = ProductProfile(ref=ref, designation=designation, category=category)
    up = normalize_text(designation)

    if NON_ORIGINAL_MARKERS.search(up):
        p.skip_reason = "produit compatible/non original : une photo officielle serait trompeuse"
        return p

    # Pack / lot (ex. "PC ... + écran HP E23") : la photo d'un seul élément tromperait.
    if re.search(r"\+\s*(ECRAN|MONITOR|MONITEUR|HP LED|CLAVIER|SOURIS|IMPRIMANTE)",
                 unicodedata.normalize("NFKD", designation).encode("ascii", "ignore").decode().upper()):
        p.skip_reason = "pack de plusieurs articles : aucune photo unique ne le représente"
        return p

    brands = detect_brands(designation)
    if not brands:
        p.skip_reason = "produit générique sans marque vérifiable"
        return p
    if len(brands) > 1:
        p.skip_reason = f"désignation ambiguë, plusieurs marques ({', '.join(sorted(brands))})"
        return p
    p.brand = brands.pop()

    brand_words = {compact(a) for a in BRANDS[p.brand]}
    p.models = [m for m in model_tokens(designation, category) if m not in brand_words]
    if not p.models:
        p.skip_reason = "aucun numéro de modèle identifiable dans la désignation"
        return p

    p.capacities = extract_capacities_gb(designation)
    p.colours = extract_colours(designation, include_tricolor=(category == "toner"), glued=True)
    return p


# --------------------------------------------------------------------------
# Candidats
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    image_url: str
    page_url: str = ""
    title: str = ""
    provider: str = ""
    width: int | None = None
    height: int | None = None

    @property
    def domain(self) -> str:
        return urlparse(self.image_url).netloc.lower()

    @property
    def is_marketplace(self) -> bool:
        both = self.domain + " " + urlparse(self.page_url).netloc.lower()
        return any(h in both for h in MARKETPLACE_HINTS)

    def evidence_text(self) -> str:
        # Page lue par le script : seul son TITRE réel fait foi (l'URL d'une
        # page peut rediriger vers un autre produit, ex. 130A -> 137A).
        if self.provider == "page":
            return " ".join([self.title or "", self.image_url or ""])
        return " ".join([self.title or "", self.page_url or "", self.image_url or ""])


@dataclass
class MatchResult:
    verdict: str
    reasons: list[str]
    score: float = 0.0


def evaluate(profile: ProductProfile, cand: Candidate) -> MatchResult:
    reasons: list[str] = []

    # 1. Source autorisée (image ET page si connue)
    if not config.domain_authorized(cand.domain) or any(
        h in cand.image_url.lower() for h in config.REJECTED_DOMAINS_HINTS
    ):
        return MatchResult(REJECT, [f"domaine image non autorisé ({cand.domain})"])
    page_domain = urlparse(cand.page_url).netloc.lower()
    if cand.page_url and not config.domain_authorized(page_domain):
        return MatchResult(REJECT, [f"page source non autorisée ({page_domain})"])

    # 2. Contexte interdit (photo de magasin, rayon...) — sur le titre
    title_words = set(tokenize(cand.title))
    bad = [t for t in config.EXCLUDED_TERMS if compact(t) in title_words]
    if bad:
        return MatchResult(REJECT, [f"terme exclu dans le titre ({', '.join(bad)})"])

    evidence = cand.evidence_text()
    cand_tokens = _candidate_token_set(evidence)

    # 3. Marque
    if profile.brand not in detect_brands(evidence) and not (
        # images servies par le CDN du fabricant lui-même (ex. hp.widen.net)
        compact(profile.brand) in compact(cand.domain)
    ):
        return MatchResult(REJECT, [f"marque {profile.brand} absente de la source"])

    # 4. Modèle principal obligatoire
    primary = profile.primary_model
    ref_token = compact(profile.ref)
    strong = list(profile.strong_tokens)
    if len(ref_token) >= 6 and re.search(r"\d", ref_token) and re.search(r"[A-Z]", ref_token):
        strong.append(ref_token)   # la référence Sage est elle-même un code constructeur
    strong_hit = [t for t in strong if t in cand_tokens or o_to_zero(t) in cand_tokens]
    if o_to_zero(primary) in cand_tokens:
        primary_found = True
    else:
        primary_found = primary in cand_tokens
    if primary_found:
        reasons.append(f"modèle '{primary}' confirmé")
    elif strong_hit:
        reasons.append(f"référence constructeur '{strong_hit[0]}' confirmée")
    else:
        return MatchResult(REJECT, [f"modèle principal '{primary}' absent de la source"])
    score = 50.0
    if len(ref_token) >= 4 and re.search(r"\d", ref_token) and ref_token in cand_tokens:
        score += 20
        reasons.append("référence exacte présente")
    score += 5 * sum(1 for m in profile.models[1:] if m in cand_tokens)

    # 4b. Photo de pack pour un article vendu à l'unité -> trompeuse
    if cand.title and _is_pack_title(cand.title) and not _is_pack_title(profile.designation):
        return MatchResult(REJECT, ["la source présente un pack/lot, l'article est vendu à l'unité"])

    # 4c. Article de papeterie vs sa recharge
    prod_up = normalize_text(profile.designation)
    if STATIONERY.search(prod_up) and cand.title:
        if bool(REFILL.search(prod_up)) != bool(REFILL.search(normalize_text(cand.title))):
            return MatchResult(REJECT, ["la source décrit l'article ou sa recharge, pas le même type de produit"])

    # 5. Original vs compatible
    if CANDIDATE_NON_ORIGINAL.search(normalize_text(cand.title)):
        return MatchResult(REJECT, ["la source décrit un produit compatible/générique"])

    verdict = ACCEPT

    # 6. Capacité
    cand_caps = extract_capacities_gb(evidence)
    if profile.capacities:
        if cand_caps and not (cand_caps & profile.capacities):
            return MatchResult(REJECT, [
                f"capacité différente (produit {sorted(profile.capacities)} Go, "
                f"source {sorted(cand_caps)} Go)"])
        if not cand_caps and profile.category == "stockage":
            verdict = REVIEW
            reasons.append("capacité non confirmée par la source")

    # 7. Couleur
    cand_colours = extract_colours(evidence, include_tricolor=(profile.category == "toner"))
    if profile.colours:
        if cand_colours and not (cand_colours & profile.colours):
            return MatchResult(REJECT, [
                f"couleur différente (produit {sorted(profile.colours)}, source {sorted(cand_colours)})"])
        if not cand_colours:   # couleur indiquée par Sage mais non confirmée par la source
            verdict = REVIEW
            reasons.append("couleur non confirmée par la source")

    # 7b. Génération du modèle (Gen 2 / G9...) quand Sage la précise
    prod_gen = extract_generations(profile.designation)
    if prod_gen:
        cand_gen = extract_generations(evidence)
        if cand_gen and not (cand_gen & prod_gen):
            return MatchResult(REJECT, [f"autre génération (produit {sorted(prod_gen)}, source {sorted(cand_gen)})"])
        if not cand_gen:
            verdict = REVIEW
            reasons.append("génération du modèle non confirmée par la source")

    # 8. Modèles voisins sur la même source (ex. page comparant A26 et A56)
    shape = re.sub(r"\d", "#", primary)
    siblings = {t for t in cand_tokens
                if t != primary and t not in profile.models
                and re.sub(r"\d", "#", t) == shape}
    if siblings and not primary.isdigit():
        verdict = REVIEW
        reasons.append(f"modèles voisins aussi cités par la source ({', '.join(sorted(siblings)[:3])})")
    # Idem pour les références constructeur (CE314A tambour vs CE310A toner)
    for strong in profile.strong_tokens:
        sshape = re.sub(r"\d", "#", strong)
        rivals = {t for t in cand_tokens if t != strong and t not in profile.models
                  and re.sub(r"\d", "#", t) == sshape}
        if rivals and strong not in cand_tokens:
            verdict = REVIEW
            reasons.append(f"la source cite une autre référence constructeur ({', '.join(sorted(rivals)[:3])}) au lieu de {strong}")

    # 9. Préférence source officielle
    score += 10 if cand.is_marketplace else 30
    if cand.width and cand.height:
        score += min(cand.width, cand.height) / 100

    return MatchResult(verdict, reasons, score)
