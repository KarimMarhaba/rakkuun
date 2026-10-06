"""Kommandozeile.

  python -m rakkuun woche [--kw N]      Wochenplan, Regelprüfung und Bestellvorschlag
  python -m rakkuun pruefen             Alle Wochen der Rotation gegen die Grundregeln prüfen
  python -m rakkuun gewicht 65.4        Gewicht eintragen (1× pro Woche, morgens, nüchtern)
  python -m rakkuun vorrat              Vorrat, Reichweite und nächster Liefertermin
  python -m rakkuun eingekauft skyr 2 --packungen   Eigenen Einkauf dazubuchen
  python -m rakkuun vorrat-setzen skyr 500          Tatsächlichen Bestand korrigieren (Gramm)
  python -m rakkuun geliefert           Zuletzt befüllten Warenkorb als geliefert buchen
  python -m rakkuun seite               Übersichtsseite (HTML) nach build/plan.html schreiben
  python -m rakkuun warenkorb           MyTime-Warenkorb mit dem Wochenbedarf befüllen (bestellt nicht)
  python -m rakkuun auto                Aus der letzten MyTime-Lieferung den nächsten Termin berechnen und
                                        bei Bedarf den Warenkorb befüllen (für den automatischen Termin)
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


TAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _datum(d: date, kurz: bool = False) -> str:
    return f"{TAGE[d.weekday()][:2]} {d:%d.%m.}" if kurz else f"{TAGE[d.weekday()]}, {d:%d.%m.%Y}"


def _stock_path(args) -> Path:
    return args.data / "vorrat.yaml"


def cmd_vorrat(args) -> int:
    from .vorrat import daily_use, load_stock, next_delivery, project
    catalog = load_catalog(args.data)
    stock = load_stock(_stock_path(args))
    today = date.today()
    now = project(stock, daily_use(catalog), today)
    plan = next_delivery(catalog, stock, today)
    at_home = set(catalog.ordering.get("zu_hause") or [])
    print("| Zutat | Bestand heute | reicht bis |")
    print("|---|---|---|")
    for ingredient_id, run_out in sorted(plan.run_out.items(), key=lambda kv: kv[1]):
        print(f"| {catalog.ingredients[ingredient_id].name} | {now.get(ingredient_id, 0):.0f} g | "
              f"{_datum(run_out, kurz=True)} |")
    if at_home:
        print("\nVon zu Hause (nicht verfolgt): " + ", ".join(catalog.ingredients[i].name for i in sorted(at_home)))
    if len(plan.limiting) == len(plan.run_out):
        reason = "Vorrat ist leer"
    else:
        reason = "zuerst leer: " + ", ".join(catalog.ingredients[i].name for i in plan.limiting)
    print(f"\nNächste Lieferung: {_datum(plan.delivery)} ({reason})")
    print(f"Warenkorb füllen und bestellen bis: {_datum(plan.fill_cart_on)}")
    return 0


def _parse_amount(catalog, ingredient_id: str, amount: float, packages: bool) -> float:
    if ingredient_id not in catalog.ingredients:
        raise SystemExit(f"Unbekannte Zutat '{ingredient_id}'. Bekannt: {', '.join(sorted(catalog.ingredients))}")
    return amount * catalog.ingredients[ingredient_id].package_g if packages else amount


def cmd_eingekauft(args) -> int:
    from .vorrat import book, load_stock, save_stock
    catalog = load_catalog(args.data)
    grams = _parse_amount(catalog, args.zutat, args.menge, args.packungen)
    stock = book(load_stock(_stock_path(args)), catalog, {args.zutat: grams})
    save_stock(_stock_path(args), stock)
    print(f"Gebucht: +{grams:.0f} g {catalog.ingredients[args.zutat].name}")
    return 0


def cmd_vorrat_setzen(args) -> int:
    from .vorrat import book, load_stock, save_stock
    catalog = load_catalog(args.data)
    grams = _parse_amount(catalog, args.zutat, args.menge, args.packungen)
    stock = book(load_stock(_stock_path(args)), catalog, {args.zutat: grams}, absolute=True)
    save_stock(_stock_path(args), stock)
    print(f"Bestand gesetzt: {grams:.0f} g {catalog.ingredients[args.zutat].name}")
    return 0


def cmd_geliefert(args) -> int:
    from .vorrat import book, load_stock, save_stock
    catalog = load_catalog(args.data)
    order = load_yaml(args.data / "letzte_befuellung.yaml")
    if not order.get("artikel") or order.get("geliefert"):
        print("Keine offene Warenkorb-Befüllung gefunden.", file=sys.stderr)
        return 1
    additions = {i: n * catalog.ingredients[i].package_g for i, n in order["artikel"].items()}
    save_stock(_stock_path(args), book(load_stock(_stock_path(args)), catalog, additions))
    order["geliefert"] = date.today().isoformat()
    save_yaml(args.data / "letzte_befuellung.yaml", order, "# Zuletzt in den MyTime-Warenkorb gelegte Artikel (Packungen)\n")
    print("Lieferung gebucht:", ", ".join(f"{n}× {catalog.ingredients[i].name}" for i, n in order["artikel"].items()))
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


def cmd_warenkorb(args) -> int:
    from .warenkorb import MyTimeShop, fill_cart, render_result, FillResult
    catalog = load_catalog(args.data)
    if args.nur_ansehen:
        with MyTimeShop() as shop:
            shop.login()
            result = FillResult()
            result.cart, result.summary = shop.cart()
        print(render_result(result))
        return 0
    from .vorrat import catalog_for_delivery, load_stock, next_delivery
    stock = load_stock(_stock_path(args))
    plan = next_delivery(catalog, stock)
    delivery = date.fromisoformat(args.lieferung) if args.lieferung else plan.delivery
    for_delivery = catalog_for_delivery(catalog, stock, delivery)
    week = generate_week(for_delivery, delivery.isocalendar().week)
    if any(f.is_error for f in validate(for_delivery, week)):
        print("❌ Der Plan verstößt gegen Grundregeln – Warenkorb wird nicht befüllt.", file=sys.stderr)
        return 1
    shopping = build_shopping_plan(for_delivery, week)
    result = fill_cart(for_delivery, shopping)
    print(f"Für die Lieferung am {_datum(delivery)} (7 Tage ab Liefertag, Vorrat abgezogen)\n")
    print(render_result(result))
    articles = {}
    for d in shopping.deliveries:
        for line in d.lines + d.filler:
            articles[line.ingredient_id] = articles.get(line.ingredient_id, 0) + line.packages
    save_yaml(args.data / "letzte_befuellung.yaml",
              {"lieferung": delivery.isoformat(), "befuellt": date.today().isoformat(), "artikel": articles},
              "# Zuletzt in den MyTime-Warenkorb gelegte Artikel (Packungen)\n")
    return 1 if result.failed else 0


def cmd_auto(args) -> int:
    """Ohne Eingaben: Die letzte Lieferung deckt 7 Tage. Die nächste soll am Tag davor kommen,
    der Warenkorb wird `vorlauf_tage` vorher befüllt. Gibt NAECHSTER_LAUF für den Termin aus."""
    from .vorrat import Stock, catalog_for_delivery, daily_use, schedule_from_last_delivery, stock_after_delivery
    from .warenkorb import MyTimeShop, fill_cart, render_result
    catalog = load_catalog(args.data)
    today = date.today()
    cover = int(catalog.ordering.get("reichweite_tage", 7))
    lead = int(catalog.ordering.get("vorlauf_tage", 2))
    with MyTimeShop() as shop:
        shop.login()
        last = shop.last_order()
    delivered = last["lieferung"] if last and last["lieferung"] else None
    delivery, fill_on, has_stock = schedule_from_last_delivery(delivered, today, cover, lead)
    stock = stock_after_delivery(catalog, delivered) if has_stock else Stock(today, {})
    if last:
        print(f"Letzte Bestellung {last['nummer']} vom {_datum(last['bestellt'])}, "
              f"Lieferung {_datum(delivered) if delivered else 'unbekannt'} ({last['status']})")
    if today < fill_on:
        print(f"Noch nichts zu tun. Nächste Lieferung am {_datum(delivery)}, Warenkorb wird am {_datum(fill_on)} befüllt.")
        print(f"NAECHSTER_LAUF={fill_on.isoformat()}")
        return 0
    for_delivery = catalog_for_delivery(catalog, stock, delivery)
    week = generate_week(for_delivery, delivery.isocalendar().week)
    if any(f.is_error for f in validate(for_delivery, week)):
        print("❌ Der Plan verstößt gegen Grundregeln – Warenkorb wird nicht befüllt.")
        print(f"NAECHSTER_LAUF={(today + timedelta(days=1)).isoformat()}")
        return 1
    result = fill_cart(for_delivery, build_shopping_plan(for_delivery, week))
    print(f"Warenkorb für die Lieferung am {_datum(delivery)} befüllt – bitte bis {_datum(delivery - timedelta(days=1))} bestellen.\n")
    print(render_result(result))
    # Nach der Bestellung rechnet der nächste Lauf ab dem echten Liefertermin weiter
    print(f"NAECHSTER_LAUF={(delivery + timedelta(days=cover - 1 - lead)).isoformat()}")
    return 1 if result.failed else 0


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

    p = sub.add_parser("vorrat", help="Vorrat, Reichweite und nächster Liefertermin")
    p.set_defaults(func=cmd_vorrat)

    for name, func, text in (("eingekauft", cmd_eingekauft, "eigenen Einkauf dazubuchen"),
                             ("vorrat-setzen", cmd_vorrat_setzen, "tatsächlichen Bestand setzen")):
        p = sub.add_parser(name, help=text)
        p.add_argument("zutat", help="Zutat-ID, z. B. skyr")
        p.add_argument("menge", type=float, help="Gramm (oder Packungen mit --packungen)")
        p.add_argument("--packungen", action="store_true")
        p.set_defaults(func=func)

    p = sub.add_parser("geliefert", help="zuletzt befüllten Warenkorb als geliefert buchen")
    p.set_defaults(func=cmd_geliefert)

    p = sub.add_parser("seite", help="Übersichtsseite als HTML erzeugen")
    p.add_argument("--kw", type=int)
    p.add_argument("--out", type=Path, default=Path("build/plan.html"))
    p.set_defaults(func=cmd_seite)

    p = sub.add_parser("auto", help="nächsten Termin aus der letzten Lieferung berechnen, ggf. Warenkorb befüllen")
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("warenkorb", help="MyTime-Warenkorb befüllen (bestellt nicht)")
    p.add_argument("--kw", type=int)
    p.add_argument("--nur-ansehen", action="store_true", help="nur einloggen und Warenkorb anzeigen")
    p.add_argument("--lieferung", help="Liefertag JJJJ-MM-TT (Standard: aus dem Vorrat berechnet)")
    p.set_defaults(func=cmd_warenkorb)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
