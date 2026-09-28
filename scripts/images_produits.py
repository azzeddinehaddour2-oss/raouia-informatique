#!/usr/bin/env python3
"""Point d'entrée du pipeline d'images produit.

    python scripts/images_produits.py --help

Voir docs/pipeline-images-produits.md pour l'installation et l'usage.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_images.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
