"""Aufruf: python -m rakkuun data/plans/beispiel-woche.yaml"""

from __future__ import annotations

import argparse
from pathlib import Path

from .data import DATA_DIR, load_catalog
from .report import render
from .shopping import build_shopping_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Wochenplan prüfen und Bestellvorschlag erstellen")
    parser.add_argument("plan", type=Path, help="Wochenplan (YAML)")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="Datenverzeichnis")
    args = parser.parse_args()

    catalog = load_catalog(args.plan, args.data)
    print(render(catalog, build_shopping_plan(catalog)))


if __name__ == "__main__":
    main()
