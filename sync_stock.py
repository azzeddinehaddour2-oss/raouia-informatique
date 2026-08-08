#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_stock.py
==============
Synchronise le catalogue produits + stocks depuis la base Sage 100
Gestion Commerciale (SQL Server) vers data/products.json, puis publie
le résultat sur GitHub Pages via git (add / commit / push) si le
fichier a réellement changé.

Utilisation :
    python sync_stock.py

Planification :
    Voir run_sync.bat + Planificateur de tâches Windows.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pyodbc

# ---------------------------------------------------------------------------
# CONFIGURATION — À ADAPTER
# ---------------------------------------------------------------------------
# Toutes les valeurs peuvent être surchargées par des variables
# d'environnement (recommandé plutôt que de coder les identifiants en dur
# dans ce fichier, surtout si le dépôt Git est public).
#
#   SAGE_SQL_SERVER    -> nom ou IP du serveur SQL Server (+ instance)
#   SAGE_SQL_DATABASE  -> nom de la base Sage 100 (ex: STOCK_26)
#   SAGE_SQL_AUTH      -> "windows" (par défaut) ou "sql"
#   SAGE_SQL_USER      -> utilisateur SQL (si SAGE_SQL_AUTH=sql)
#   SAGE_SQL_PASSWORD  -> mot de passe SQL (si SAGE_SQL_AUTH=sql)
#   SAGE_DEPOT         -> code dépôt à filtrer (optionnel, vide = tous)
#
# Exemple pour définir une variable d'environnement avant exécution
# (PowerShell) :
#   $env:SAGE_SQL_SERVER = "SRV-SAGE\SAGE100"
#
CONFIG = {
    # Nom du serveur SQL Server. Valeur reprise de la config déjà
    # fonctionnelle de C:\Sage\ClaudeAutomation\scripts\daemon_notif_stock26.py
    # (daemon de surveillance STOCK_26 tournant sur cette même machine).
    "server": os.environ.get("SAGE_SQL_SERVER", "localhost"),

    # Nom de la base de données Sage 100 utilisée par le daemon de
    # surveillance existant. Changer ici si le catalogue boutique doit
    # provenir d'une autre base Sage.
    "database": os.environ.get("SAGE_SQL_DATABASE", "STOCK_26"),

    # "windows" = authentification Windows intégrée (Trusted_Connection),
    # "sql"     = authentification SQL Server classique (user/mdp).
    "auth_mode": os.environ.get("SAGE_SQL_AUTH", "windows"),

    "user": os.environ.get("SAGE_SQL_USER", ""),
    "password": os.environ.get("SAGE_SQL_PASSWORD", ""),

    # Pilote ODBC installé sur la machine. Vérifier avec :
    #   python -c "import pyodbc; print(pyodbc.drivers())"
    "driver": os.environ.get("SAGE_SQL_DRIVER", "{ODBC Driver 17 for SQL Server}"),

    # Code dépôt Sage à filtrer dans F_ARTSTOCK (laisser vide pour
    # sommer le stock de tous les dépôts).
    "depot": os.environ.get("SAGE_DEPOT", ""),
}

# ---------------------------------------------------------------------------
# CHEMINS
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = REPO_ROOT / "data" / "products.json"

# ---------------------------------------------------------------------------
# REQUÊTE SQL
# ---------------------------------------------------------------------------
# F_ARTICLE   : fiche article (référence, désignation, prix de vente)
# F_ARTSTOCK  : stock réel par article / par dépôt
#
# Le stock est sommé sur tous les dépôts sauf si CONFIG["depot"] est
# renseigné, auquel cas seul ce dépôt est pris en compte.
#
# Exclusions d'articles internes/tests, non destinés à la boutique publique :
#   - FA_CodeFamille = 'SER'  : codes de service internes par employé
#                               (ex: "SERVICE YOUSEFFE", "SERVICE AZZEDDINE").
#                               Les familles de services facturables restent
#                               affichées (ex: LOCATION).
#   - AR_Design contient 'SERVICE' : filet de sécurité complémentaire pour les
#                               articles de service hors famille SER (ex:
#                               "01-SANAE / SERVICE SOUMIA", famille TON).
#                               ATTENTION : ceci exclut aussi tout article
#                               légitime dont la désignation contient le mot
#                               "service" (ex: "installation et mise en
#                               service"). Retirer cette ligne si besoin.
#   - AR_Ref IN ('101010','1011') : références de test / usage interne
#                               identifiées manuellement (article de test,
#                               pièce de caisse comptable).
#   - AR_Sommeil = 1          : article mis en sommeil dans Sage (inactif).
SQL_QUERY = """
SELECT
    a.AR_Ref                         AS AR_Ref,
    a.AR_Design                      AS AR_Design,
    a.AR_PrixVen                     AS AR_PrixVen,
    ISNULL(SUM(s.AS_QteSto), 0)      AS AS_QteSto
FROM F_ARTICLE a
LEFT JOIN F_ARTSTOCK s
    ON s.AR_Ref = a.AR_Ref
    {depot_filter}
WHERE a.AR_Ref <> ''
  AND (a.FA_CodeFamille IS NULL OR a.FA_CodeFamille <> 'SER')
  AND a.AR_Design NOT LIKE '%SERVICE%'
  AND a.AR_Ref NOT IN ('101010', '1011')
  AND ISNULL(a.AR_Sommeil, 0) = 0
GROUP BY a.AR_Ref, a.AR_Design, a.AR_PrixVen
ORDER BY a.AR_Ref
"""


def build_connection_string() -> str:
    cfg = CONFIG
    base = f"DRIVER={cfg['driver']};SERVER={cfg['server']};DATABASE={cfg['database']};"
    if cfg["auth_mode"].lower() == "sql":
        return base + f"UID={cfg['user']};PWD={cfg['password']};"
    return base + "Trusted_Connection=yes;"


def fetch_products_from_sage() -> list[dict]:
    """Se connecte à Sage 100 et retourne la liste des produits/stocks."""
    depot_filter = ""
    params: list = []
    if CONFIG["depot"]:
        depot_filter = "AND s.DE_No = ?"
        params.append(CONFIG["depot"])

    query = SQL_QUERY.format(depot_filter=depot_filter)

    conn_str = build_connection_string()
    print(f"Connexion à {CONFIG['server']} / {CONFIG['database']} ...")
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params) if params else cursor.execute(query)
        rows = cursor.fetchall()

    products = []
    for row in rows:
        ref = (row.AR_Ref or "").strip()
        if not ref:
            continue
        products.append(
            {
                "ref": ref,
                "designation": (row.AR_Design or "").strip(),
                "prix": float(row.AR_PrixVen) if row.AR_PrixVen is not None else 0.0,
                "stock": int(row.AS_QteSto) if row.AS_QteSto is not None else 0,
            }
        )
    return products


def write_products_json(products: list[dict]) -> bool:
    """Écrit data/products.json. Retourne True si le contenu a changé."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(products),
        "products": products,
    }
    new_content = json.dumps(payload, ensure_ascii=False, indent=2)

    old_content = None
    if OUTPUT_PATH.exists():
        old_content = OUTPUT_PATH.read_text(encoding="utf-8")

    # Compare en ignorant le champ "generated_at" pour ne committer que
    # les vrais changements de données (référence, prix, stock, ajout...).
    changed = True
    if old_content is not None:
        try:
            old_payload = json.loads(old_content)
            changed = old_payload.get("products") != products
        except json.JSONDecodeError:
            changed = True

    OUTPUT_PATH.write_text(new_content, encoding="utf-8")
    return changed


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


def push_to_github() -> None:
    """git add / commit / push de data/products.json si des changements existent."""
    add = git("add", "data/products.json")
    if add.returncode != 0:
        print("Erreur 'git add' :", add.stderr, file=sys.stderr)
        return

    status = git("status", "--porcelain", "data/products.json")
    if not status.stdout.strip():
        print("Aucun changement Git à committer.")
        return

    commit = git("commit", "-m", "auto: mise à jour des stocks et prix Sage 100")
    if commit.returncode != 0:
        print("Erreur 'git commit' :", commit.stderr, file=sys.stderr)
        return
    print(commit.stdout.strip())

    push = git("push", "origin", "main")
    if push.returncode != 0:
        print("Erreur 'git push' :", push.stderr, file=sys.stderr)
        return
    print("Push GitHub effectué avec succès.")


def main() -> int:
    try:
        products = fetch_products_from_sage()
    except pyodbc.Error as exc:
        print(f"Erreur de connexion/requête Sage 100 : {exc}", file=sys.stderr)
        return 1

    print(f"{len(products)} article(s) récupéré(s) depuis Sage 100.")

    changed = write_products_json(products)
    if not changed:
        print("Aucun changement de données détecté, pas de commit.")
        return 0

    print("Changements détectés dans data/products.json.")
    push_to_github()
    return 0


if __name__ == "__main__":
    sys.exit(main())
