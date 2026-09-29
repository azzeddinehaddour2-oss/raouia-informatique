"""Orchestration : sélection des produits, évaluation des candidats,
téléchargement/optimisation, mise à jour du catalogue et file de revue."""

import html
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import catalog, config, imaging
from .matching import ACCEPT, REJECT, REVIEW, Candidate, build_profile, evaluate

log = logging.getLogger("product_images")


@dataclass
class Outcome:
    status: str                      # "ok" | "review" | "none"
    entry: dict | None = None
    review: list[dict] = field(default_factory=list)
    reason: str = ""


def _review_item(cand: Candidate, reasons: list[str], score: float) -> dict:
    return {"image_url": cand.image_url, "page_url": cand.page_url, "title": cand.title,
            "provider": cand.provider, "score": round(score, 1), "reasons": reasons}


def _used_origins(images: dict) -> dict:
    return {e.get("origin_url") or e.get("image"): r for r, e in images.items()
            if e.get("source") in ("local", "web")}


def _same_product(a, b) -> bool:
    """Deux fiches Sage du même article (config/stock différents) : même
    marque, même modèle principal, mêmes couleurs."""
    return (a.brand == b.brand and a.primary_model == b.primary_model
            and a.name_words == b.name_words
            and a.colours == b.colours and not a.skip_reason and not b.skip_reason)


def process_candidates(profile, candidates, all_refs, dry_run: bool, used_origins=None,
                       designations=None) -> Outcome:
    """Évalue tous les candidats, télécharge le meilleur ACCEPT qui passe le
    contrôle qualité. Le moindre doute bascule en file de revue."""
    accepted, review = [], []
    seen = set()
    for cand in candidates:
        if not cand.image_url or cand.image_url in seen:
            continue
        seen.add(cand.image_url)
        res = evaluate(profile, cand)
        log.debug("  [%s] %s -> %s (%s)", profile.ref, cand.image_url[:90], res.verdict, "; ".join(res.reasons))
        if res.verdict == ACCEPT:
            accepted.append((res.score, cand, res.reasons))
        elif res.verdict == REVIEW:
            review.append((res.score, cand, res.reasons))

    accepted.sort(key=lambda x: -x[0])
    used = used_origins or {}
    for score, cand, reasons in accepted:
        other = used.get(cand.image_url)
        if other and other != profile.ref and not (
                designations and _same_product(profile, build_profile(other, designations.get(other, "")))):
            # Une photo déjà attribuée à un autre article ne peut pas être
            # "exacte" pour deux références différentes (incident Samsung 08/2026).
            review.append((score, cand, reasons + [f"image déjà utilisée pour {other}"]))
            continue
        try:
            img = imaging.download(cand.image_url)
        except imaging.ImageError as exc:
            log.info("  [%s] candidat écarté : %s", profile.ref, exc)
            continue
        _, problems = imaging.check_quality(img)
        if problems:
            review.append((score, cand, reasons + problems))
            continue
        dest = catalog.output_path_for(profile.ref, all_refs)
        if dry_run:
            dest = dest.with_suffix("." + config.OUTPUT_FORMAT)
        else:
            dest = imaging.optimize_and_save(img, dest)
        entry = catalog.local_entry(dest, cand.image_url, cand.page_url, "auto")
        return Outcome("ok", entry=entry, reason="; ".join(reasons))

    if review:
        review.sort(key=lambda x: -x[0])
        items = [_review_item(c, r, s) for s, c, r in review[: config.MAX_REVIEW_CANDIDATES]]
        return Outcome("review", review=items, reason="correspondance non prouvée à 100 %")
    return Outcome("none", reason="aucun candidat conforme")


def _queue_for_review(queue: dict, profile, items: list[dict], origin: str) -> None:
    queue[profile.ref] = {
        "designation": profile.designation,
        "origin": origin,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "candidates": items,
    }


# --------------------------------------------------------------------------
# Commande : search
# --------------------------------------------------------------------------

def run_search(providers, limit: int, refs: list[str] | None, dry_run: bool,
               products_source: Path | None = None, retry_attempted: bool = False) -> dict:
    products = catalog.load_products(products_source)
    images = catalog.load_images()
    attempted = catalog.load_attempted()
    queue = catalog.load_review_queue()
    all_refs = [p["ref"] for p in products]

    stats = {"traites": 0, "images": 0, "revue": 0, "rien": 0, "ignores": 0}
    for p in products:
        if stats["traites"] >= limit:
            break
        ref = p["ref"]
        if refs and ref not in refs:
            continue
        current = images.get(ref, {})
        if not refs:
            if current.get("source") in ("local", "web"):
                continue
            if ref in attempted and not retry_attempted:
                continue
            if ref in queue:
                continue

        profile = build_profile(ref, p["designation"])
        if profile.skip_reason:
            stats["ignores"] += 1
            if refs:
                log.info("[%s] ignoré : %s", ref, profile.skip_reason)
            continue

        stats["traites"] += 1
        log.info("[%s] %s | requête : %s", ref, p["designation"], profile.search_query())
        candidates = []
        for prov in providers:
            try:
                candidates += prov.search(profile)
            except Exception as exc:  # noqa: BLE001 - un fournisseur en panne ne bloque pas les autres
                log.warning("[%s] fournisseur %s en erreur : %s", ref, prov.name, exc)

        outcome = process_candidates(profile, candidates, all_refs, dry_run, _used_origins(images),
                                     {x["ref"]: x["designation"] for x in products})
        attempted.add(ref)
        if outcome.status == "ok":
            stats["images"] += 1
            log.info("[%s] OK -> %s (%s)", ref, outcome.entry["image"], outcome.reason)
            images[ref] = outcome.entry
            queue.pop(ref, None)
        elif outcome.status == "review":
            stats["revue"] += 1
            log.warning("[%s] ALERTE validation manuelle requise : %s", ref, outcome.reason)
            _queue_for_review(queue, profile, outcome.review, "search")
            images.setdefault(ref, catalog.placeholder_entry(p["designation"]))
        else:
            stats["rien"] += 1
            log.info("[%s] placeholder conservé : %s", ref, outcome.reason)
            images.setdefault(ref, catalog.placeholder_entry(p["designation"]))

    if not dry_run:
        catalog.save_images(images)
        catalog.save_attempted(attempted)
        catalog.save_review_queue(queue)
        catalog.sync_products_json(images)
    return stats


# --------------------------------------------------------------------------
# Commande : localize (liens "web" existants -> fichiers locaux optimisés)
# --------------------------------------------------------------------------

def run_localize(dry_run: bool, refs: list[str] | None = None) -> dict:
    products = {p["ref"]: p for p in catalog.load_products()}
    images = catalog.load_images()
    queue = catalog.load_review_queue()
    all_refs = list(products)

    stats = {"localisees": 0, "revue": 0, "retirees": 0}
    for ref, entry in list(images.items()):
        if entry.get("source") != "web" or (refs and ref not in refs):
            continue
        designation = products.get(ref, {}).get("designation", "")
        profile = build_profile(ref, designation)
        cand = Candidate(image_url=entry["image"], page_url=entry.get("source_page") or "",
                         title="", provider="existant")

        # Contradiction prouvée -> photo retirée. Simple manque de preuve
        # (modèle absent de l'URL, marque non répertoriée...) -> placeholder
        # + validation manuelle : un humain tranche, rien n'est perdu.
        if profile.skip_reason:
            if "non original" in profile.skip_reason:
                stats["retirees"] += 1
                log.warning("[%s] photo retirée : %s (%s)", ref, profile.skip_reason, designation)
            else:
                stats["revue"] += 1
                log.warning("[%s] ALERTE validation manuelle : %s", ref, profile.skip_reason)
                _queue_for_review(queue, profile, [_review_item(cand, [profile.skip_reason], 0)], "localize")
            images[ref] = catalog.placeholder_entry(designation)
            continue

        res = evaluate(profile, cand)
        if res.verdict == REJECT:
            missing_proof = any(r.startswith(("modèle principal", "marque ")) for r in res.reasons)
            if missing_proof:
                stats["revue"] += 1
                log.warning("[%s] ALERTE validation manuelle : %s", ref, "; ".join(res.reasons))
                _queue_for_review(queue, profile, [_review_item(cand, res.reasons, 0)], "localize")
            else:
                stats["retirees"] += 1
                log.warning("[%s] photo retirée : %s", ref, "; ".join(res.reasons))
            images[ref] = catalog.placeholder_entry(designation)
            continue

        outcome = process_candidates(profile, [cand], all_refs, dry_run) if res.verdict == ACCEPT \
            else Outcome("review", review=[_review_item(cand, res.reasons, res.score)],
                         reason="; ".join(res.reasons))
        if outcome.status == "ok":
            stats["localisees"] += 1
            images[ref] = outcome.entry
        else:
            # Au moindre doute : placeholder + validation manuelle.
            stats["revue"] += 1
            reason = outcome.reason if outcome.status == "review" else outcome.reason
            items = outcome.review or [_review_item(cand, [reason], res.score)]
            log.warning("[%s] ALERTE validation manuelle : %s", ref, "; ".join(items[0]["reasons"]))
            _queue_for_review(queue, profile, items, "localize")
            images[ref] = catalog.placeholder_entry(designation)

    if not dry_run:
        catalog.save_images(images)
        catalog.save_review_queue(queue)
        catalog.sync_products_json(images)
    return stats


# --------------------------------------------------------------------------
# Validation manuelle
# --------------------------------------------------------------------------

def approve(ref: str, index: int = 1, image_url: str | None = None, page_url: str = "",
            trusted: bool = False) -> str:
    """Valide manuellement un candidat de la file (ou une URL fournie).
    trusted=True : revendeur hors liste blanche, accepté uniquement après
    contrôle visuel ET preuve texte (code fabricant ou marque + nom exacts
    dans le titre de la page) — tracé "manuel-visuel"."""
    products = {p["ref"]: p for p in catalog.load_products()}
    if ref not in products:
        raise ValueError(f"référence inconnue : {ref}")
    queue = catalog.load_review_queue()
    if image_url is None:
        item = queue.get(ref, {}).get("candidates", [])[index - 1:index]
        if not item:
            raise ValueError(f"aucun candidat n°{index} en attente pour {ref}")
        image_url, page_url = item[0]["image_url"], item[0].get("page_url", "")
    # liste blanche (sauf revendeur vérifié à la main) + intégrité toujours imposées
    img = imaging.download(image_url, authorized=(lambda d: True) if trusted else None)
    _, problems = imaging.check_quality(img)
    if problems:
        log.warning("[%s] validé manuellement malgré : %s", ref, "; ".join(problems))
    dest = imaging.optimize_and_save(img, catalog.output_path_for(ref, list(products)))
    images = catalog.load_images()
    images[ref] = catalog.local_entry(dest, image_url, page_url, "manuel-visuel" if trusted else "manuel")
    catalog.save_images(images)
    queue.pop(ref, None)
    catalog.save_review_queue(queue)
    catalog.sync_products_json(images)
    attempted = catalog.load_attempted()
    attempted.add(ref)
    catalog.save_attempted(attempted)
    return images[ref]["image"]


def revoke(ref: str, reason: str) -> None:
    """Retire une image validée à tort (ex. contrôle visuel : la page
    officielle affiche un autre produit). Placeholder + validation manuelle."""
    products = {p["ref"]: p for p in catalog.load_products()}
    images = catalog.load_images()
    entry = images.get(ref, {})
    if entry.get("source") not in ("local", "web"):
        raise ValueError(f"{ref} n'a pas d'image à retirer")
    if entry.get("source") == "local":
        (config.REPO_ROOT / entry["image"]).unlink(missing_ok=True)
    designation = products.get(ref, {}).get("designation", "")
    images[ref] = catalog.placeholder_entry(designation)
    catalog.save_images(images)
    queue = catalog.load_review_queue()
    profile = build_profile(ref, designation)
    _queue_for_review(queue, profile, [{
        "image_url": entry.get("origin_url") or entry.get("image"), "page_url": entry.get("source_page") or "",
        "title": "", "provider": "revoque", "score": 0, "reasons": [f"retirée : {reason}"]}], "revoke")
    catalog.save_review_queue(queue)
    catalog.sync_products_json(images)
    log.warning("[%s] image retirée : %s", ref, reason)


def reject(ref: str) -> None:
    queue = catalog.load_review_queue()
    queue.pop(ref, None)
    catalog.save_review_queue(queue)
    attempted = catalog.load_attempted()
    attempted.add(ref)
    catalog.save_attempted(attempted)


def write_review_page(dest: Path) -> Path:
    """Page HTML locale pour comparer visuellement produit et candidats."""
    queue = catalog.load_review_queue()
    rows = []
    for ref, item in sorted(queue.items()):
        cards = []
        for i, c in enumerate(item["candidates"], 1):
            cards.append(
                f'<figure><img src="{html.escape(c["image_url"])}" loading="lazy">'
                f'<figcaption><b>n°{i}</b> — score {c["score"]}<br>{html.escape(c.get("title") or "")}'
                f'<br><small>{html.escape("; ".join(c["reasons"]))}</small>'
                f'<br><a href="{html.escape(c.get("page_url") or c["image_url"])}" target="_blank">source</a>'
                f'<br><code>python scripts/images_produits.py review approve "{html.escape(ref)}" {i}</code>'
                f'</figcaption></figure>')
        rows.append(
            f'<section><h2>{html.escape(ref)} — {html.escape(item["designation"])}</h2>'
            f'<div class="c">{"".join(cards)}</div>'
            f'<code>python scripts/images_produits.py review reject "{html.escape(ref)}"</code></section>')
    page = (
        "<!doctype html><meta charset=utf-8><title>Validation images produits</title>"
        "<style>body{font:14px system-ui;margin:24px;background:#f8fafc;color:#0f172a}"
        "section{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin:0 0 16px}"
        ".c{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0;width:260px}"
        "img{width:260px;height:260px;object-fit:contain;background:#fff;border:1px solid #e2e8f0}"
        "code{display:block;background:#f1f5f9;padding:4px 6px;margin-top:4px;font-size:12px;word-break:break-all}</style>"
        f"<h1>Validation manuelle — {len(queue)} produit(s) en attente</h1>"
        + ("".join(rows) or "<p>Rien à valider.</p>"))
    dest.write_text(page, encoding="utf-8")
    return dest
