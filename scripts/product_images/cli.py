"""Ligne de commande : python scripts/images_produits.py <commande> ...

  search    Cherche des images pour les produits encore en placeholder.
  localize  Télécharge/optimise les photos "web" déjà validées (hotlinks)
            pour les héberger sur le site, en les re-validant strictement.
  review    Validation manuelle : list | html | approve REF [N] | reject REF.
  check     Diagnostic d'un produit : profil extrait et verdict d'une URL.
"""

import argparse
import sys
from pathlib import Path

from . import catalog, config, pipeline
from .matching import Candidate, build_profile, evaluate
from .providers import build_providers


def _refs(value: str | None) -> list[str] | None:
    return [r.strip() for r in value.split(",") if r.strip()] if value else None


def cmd_search(args) -> int:
    providers = build_providers(args.providers.split(","), args.candidates)
    if not providers:
        print("Aucun fournisseur de recherche utilisable (voir clés API dans la doc).", file=sys.stderr)
        return 2
    stats = pipeline.run_search(providers, args.limit, _refs(args.refs), args.dry_run,
                                args.products, args.retry)
    print(f"\nRésultat : {stats}" + ("  [dry-run : rien n'a été écrit]" if args.dry_run else ""))
    return 0


def cmd_localize(args) -> int:
    stats = pipeline.run_localize(args.dry_run, _refs(args.refs))
    print(f"\nRésultat : {stats}" + ("  [dry-run : rien n'a été écrit]" if args.dry_run else ""))
    return 0


def cmd_review(args) -> int:
    if args.action == "list":
        queue = catalog.load_review_queue()
        if not queue:
            print("Aucun produit en attente de validation.")
        for ref, item in sorted(queue.items()):
            print(f"\n{ref} — {item['designation']}  ({item['origin']}, {item['added_at']})")
            for i, c in enumerate(item["candidates"], 1):
                print(f"  n°{i} score {c['score']} : {c['image_url']}")
                print(f"       page : {c.get('page_url') or '-'}")
                print(f"       motif : {'; '.join(c['reasons'])}")
    elif args.action == "html":
        dest = pipeline.write_review_page(config.REPO_ROOT / "scripts" / "images_review.html")
        print(f"Page de validation : {dest}")
    elif args.action == "approve":
        path = pipeline.approve(args.ref, args.index, args.url, args.page or "")
        print(f"{args.ref} validé -> {path}")
    elif args.action == "revoke":
        pipeline.revoke(args.ref, args.reason)
        print(f"{args.ref} : image retirée, placeholder remis, en attente de validation manuelle.")
    elif args.action == "reject":
        pipeline.reject(args.ref)
        print(f"{args.ref} rejeté : placeholder conservé, ne sera plus recherché.")
    return 0


def cmd_check(args) -> int:
    products = {p["ref"]: p for p in catalog.load_products()}
    if args.ref not in products:
        print(f"Référence inconnue : {args.ref}", file=sys.stderr)
        return 2
    prof = build_profile(args.ref, products[args.ref]["designation"])
    print(f"Désignation : {prof.designation}\nCatégorie   : {prof.category}")
    if prof.skip_reason:
        print(f"IGNORÉ      : {prof.skip_reason}")
        return 0
    print(f"Marque      : {prof.brand}\nModèles     : {prof.models}")
    print(f"Capacités   : {sorted(prof.capacities)} Go\nCouleurs    : {sorted(prof.colours)}")
    print(f"Requête     : {prof.search_query()}")
    if args.url:
        res = evaluate(prof, Candidate(args.url, args.page or "", args.title or ""))
        print(f"\nVerdict     : {res.verdict.upper()} (score {res.score:.0f})")
        for r in res.reasons:
            print(f"  - {r}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="images_produits", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true", help="détail de chaque candidat")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="rechercher des images pour les produits en placeholder")
    s.add_argument("--providers", default="brave", help="brave,google,file (défaut : brave)")
    s.add_argument("--candidates", type=Path, help="fichier JSON de candidats (fournisseur 'file')")
    s.add_argument("--products", type=Path, help="source produits JSON ou CSV (défaut data/products.json)")
    s.add_argument("--limit", type=int, default=20, help="nombre max de produits traités")
    s.add_argument("--refs", help="références précises, séparées par des virgules")
    s.add_argument("--retry", action="store_true", help="retenter les références déjà tentées")
    s.add_argument("--dry-run", action="store_true", help="n'écrit ni image ni fichier de données")
    s.set_defaults(func=cmd_search)

    l = sub.add_parser("localize", help="héberger localement les photos 'web' existantes")
    l.add_argument("--refs", help="références précises, séparées par des virgules")
    l.add_argument("--dry-run", action="store_true")
    l.set_defaults(func=cmd_localize)

    r = sub.add_parser("review", help="validation manuelle")
    r.add_argument("action", choices=["list", "html", "approve", "reject", "revoke"])
    r.add_argument("ref", nargs="?")
    r.add_argument("index", nargs="?", type=int, default=1, help="n° du candidat (approve)")
    r.add_argument("--url", help="approve : URL d'image fournie à la main (domaine autorisé)")
    r.add_argument("--page", help="approve : page source de l'URL fournie")
    r.add_argument("--reason", default="image incorrecte (contrôle visuel)", help="revoke : motif")
    r.set_defaults(func=cmd_review)

    c = sub.add_parser("check", help="diagnostic d'une référence / d'une URL candidate")
    c.add_argument("ref")
    c.add_argument("--url")
    c.add_argument("--page")
    c.add_argument("--title")
    c.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if args.command == "review" and args.action in ("approve", "reject", "revoke") and not args.ref:
        parser.error("review approve/reject nécessite une référence")
    catalog.setup_logging(args.verbose)
    return args.func(args)
