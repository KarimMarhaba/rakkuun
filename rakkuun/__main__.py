"""Kommandozeile.

  python -m rakkuun woche [--kw N]      Wochenplan, Regelprüfung und Bestellvorschlag
  python -m rakkuun pruefen             Alle Wochen der Rotation gegen die Grundregeln prüfen
  python -m rakkuun gewicht 65.4        Gewicht eintragen (1× pro Woche, morgens, nüchtern)
  python -m rakkuun vorrat-buchen       Nach bestätigter Bestellung den Vorrat fortschreiben
  python -m rakkuun seite               Übersichtsseite (HTML) nach build/plan.html schreiben
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .data import DATA_DIR, load_catalog, load_yaml, save_yaml
from .plan import generate_week
from .report import render, render_findings
from .rules import validate
from .shopping import build_shopping_plan


def _next_week() -> int:
    return (date.today() + timedelta(days=7)).isocalendar().week


def cmd_woche(args) -> int:
    catalog = load_catalog(args.data)
    week = generate_week(catalog, args.kw or _next_week())
    findings = validate(catalog, week)
    ok = not any(f.is_error for f in findings)
    print(render(catalog, week, findings, build_shopping_plan(catalog, week) if ok else None))
    return 0 if ok else 1


def cmd_pruefen(args) -> int:
    try:
        catalog = load_catalog(args.data)
    except (ValueError, KeyError, TypeError) as e:
        print(f"❌ Daten fehlerhaft: {e}", file=sys.stderr)
        return 1
    rotation = len(catalog.template.get("huelsenfrucht_rotation") or []) or 1
    failed = False
    for kw in range(rotation):
        week = generate_week(catalog, kw)
        findings = validate(catalog, week)
        errors = [f for f in findings if f.is_error]
        label = catalog.ingredients[week.legume].name if week.legume else f"Variante {kw}"
        print(f"### Rotation: {label}")
        print("\n".join(render_findings(findings if args.alle else errors) if (errors or args.alle)
                        else ["✅ Alle Grundregeln eingehalten."]))
        failed |= bool(errors)
    return 1 if failed else 0


def cmd_gewicht(args) -> int:
    path = args.data / "gewicht.yaml"
    weights = {str(k): v for k, v in load_yaml(path).items()}
    weights[args.datum or date.today().isoformat()] = args.kg
    save_yaml(path, weights, "# 1× pro Woche wiegen: morgens, nüchtern. Format: JJJJ-MM-TT: kg\n")
    print(f"Eingetragen: {args.kg} kg")
    return 0


def cmd_vorrat_buchen(args) -> int:
    catalog = load_catalog(args.data)
    week = generate_week(catalog, args.kw or _next_week())
    shopping = build_shopping_plan(catalog, week)
    save_yaml(args.data / "vorrat.yaml", shopping.pantry_after,
              "# Was noch zu Hause ist (Gramm). Wird nach jeder bestätigten Bestellung fortgeschrieben.\n")
    print("Vorrat nach dieser Woche:", shopping.pantry_after)
    return 0


def cmd_seite(args) -> int:
    from .site import render_site
    catalog = load_catalog(args.data)
    week = generate_week(catalog, args.kw or _next_week())
    findings = validate(catalog, week)
    ok = not any(f.is_error for f in findings)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_site(catalog, week, findings, build_shopping_plan(catalog, week) if ok else None),
                        encoding="utf-8")
    print(f"Seite geschrieben: {args.out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="rakkuun", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="Datenverzeichnis")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("woche", help="Wochenplan und Bestellvorschlag")
    p.add_argument("--kw", type=int, help="Kalenderwoche (Standard: nächste Woche)")
    p.set_defaults(func=cmd_woche)

    p = sub.add_parser("pruefen", help="Grundregeln prüfen")
    p.add_argument("--alle", action="store_true", help="auch Hinweise anzeigen")
    p.set_defaults(func=cmd_pruefen)

    p = sub.add_parser("gewicht", help="Gewicht eintragen")
    p.add_argument("kg", type=float)
    p.add_argument("--datum", help="JJJJ-MM-TT (Standard: heute)")
    p.set_defaults(func=cmd_gewicht)

    p = sub.add_parser("vorrat-buchen", help="Vorrat nach bestätigter Bestellung fortschreiben")
    p.add_argument("--kw", type=int)
    p.set_defaults(func=cmd_vorrat_buchen)

    p = sub.add_parser("seite", help="Übersichtsseite als HTML erzeugen")
    p.add_argument("--kw", type=int)
    p.add_argument("--out", type=Path, default=Path("build/plan.html"))
    p.set_defaults(func=cmd_seite)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
