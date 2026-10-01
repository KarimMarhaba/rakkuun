"""Vorratsplanung: Was ist noch da, wann geht es aus, wann muss die nächste Lieferung kommen?

Der Vorrat wird mit Datum gespeichert (data/vorrat.yaml). Von dort aus wird mit dem täglichen
Verbrauch laut Plan hochgerechnet. Die nächste Lieferung soll an dem Tag kommen, bevor die erste
bestellte Zutat ausgeht. Eigene Einkäufe und Lieferungen werden dazugebucht, damit die Rechnung stimmt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .data import WEEKDAYS, Catalog, load_yaml, save_yaml
from .plan import day_grams, generate_week

HEADER = ("# Vorrat zu Hause (Gramm) zum Stichtag 'stand'. Wird bei Lieferungen und eigenen Einkäufen\n"
          "# fortgeschrieben; der Verbrauch dazwischen wird aus dem Plan hochgerechnet.\n")


@dataclass
class Stock:
    as_of: date
    grams: dict[str, float]


def load_stock(path: Path) -> Stock:
    raw = load_yaml(path)
    if "bestand" in raw:
        return Stock(date.fromisoformat(str(raw["stand"])), {k: float(v) for k, v in (raw["bestand"] or {}).items()})
    # altes Format ohne Stichtag: Mengen gelten ab heute
    return Stock(date.today(), {k: float(v) for k, v in raw.items()})


def save_stock(path: Path, stock: Stock) -> None:
    data = {"stand": stock.as_of.isoformat(),
            "bestand": {k: round(v) for k, v in sorted(stock.grams.items()) if v >= 1}}
    save_yaml(path, data, HEADER)


def daily_use(catalog: Catalog) -> dict[str, float]:
    """Durchschnittlicher Tagesverbrauch laut Plan (über eine Woche gemittelt)."""
    week = generate_week(catalog, date.today().isocalendar().week)
    total: dict[str, float] = {}
    for day in week.days:
        for ingredient_id, grams in day_grams(catalog, day).items():
            total[ingredient_id] = total.get(ingredient_id, 0) + grams
    return {i: g / len(week.days) for i, g in total.items()}


def project(stock: Stock, use: dict[str, float], on: date) -> dict[str, float]:
    """Voraussichtlicher Bestand am Morgen von `on`."""
    days = max((on - stock.as_of).days, 0)
    return {i: max(stock.grams.get(i, 0.0) - use.get(i, 0.0) * days, 0.0)
            for i in set(stock.grams) | set(use)}


def runs_out(stock: Stock, use: dict[str, float]) -> dict[str, date]:
    """Erster Tag, an dem der Bestand nicht mehr für den Tagesbedarf reicht."""
    return {i: stock.as_of + timedelta(days=math.floor(stock.grams.get(i, 0.0) / per_day + 1e-9))
            for i, per_day in use.items() if per_day > 0}


@dataclass
class Schedule:
    delivery: date            # Lieferung soll an diesem Tag ankommen
    fill_cart_on: date        # spätestens dann Warenkorb füllen und bestellen
    limiting: list[str]       # Zutaten, die zuerst ausgehen
    run_out: dict[str, date]


def next_delivery(catalog: Catalog, stock: Stock, today: date | None = None) -> Schedule:
    today = today or date.today()
    use = daily_use(catalog)
    at_home = set(catalog.ordering.get("zu_hause") or [])
    run_out = {i: d for i, d in runs_out(stock, use).items() if i not in at_home}
    first = min(run_out.values())
    # Lieferung am Tag bevor etwas ausgeht – aber nicht in der Vergangenheit
    delivery = max(first - timedelta(days=1), today)
    lead = int(catalog.ordering.get("vorlauf_tage", 2))
    fill_on = max(delivery - timedelta(days=lead), today)
    limiting = sorted(i for i, d in run_out.items() if d == first)
    return Schedule(delivery, fill_on, limiting, run_out)


def catalog_for_delivery(catalog: Catalog, stock: Stock, delivery: date) -> Catalog:
    """Katalog, dessen Woche am Liefertag beginnt und dessen Vorrat der Bestand an diesem Tag ist."""
    from copy import copy
    c = copy(catalog)
    c.settings = {**catalog.settings, "bestellung": {**catalog.ordering, "liefertag": WEEKDAYS[delivery.weekday()]}}
    c.pantry = {i: g for i, g in project(stock, daily_use(catalog), delivery).items() if g >= 1}
    return c


def book(stock: Stock, catalog: Catalog, additions: dict[str, float], on: date | None = None,
         absolute: bool = False) -> Stock:
    """Lieferung/Einkauf dazubuchen (oder mit absolute=True den Bestand direkt setzen)."""
    on = on or date.today()
    current = project(stock, daily_use(catalog), on) if on >= stock.as_of else dict(stock.grams)
    for ingredient_id, grams in additions.items():
        current[ingredient_id] = grams if absolute else current.get(ingredient_id, 0.0) + grams
    return Stock(on, {i: g for i, g in current.items() if g >= 1})


def schedule_from_last_delivery(delivered: date | None, today: date, cover: int = 7,
                                lead: int = 2) -> tuple[date, date, bool]:
    """Liefertermin und Befüll-Tag aus der letzten Lieferung.

    Eine Lieferung deckt `cover` Tage; die nächste soll am letzten Tag kommen, an dem noch etwas da ist.
    Rückgabe: (nächste Lieferung, Tag zum Befüllen des Warenkorbs, ob noch Vorrat aus der letzten Lieferung da ist).
    """
    if delivered and delivered + timedelta(days=cover - 1) > today:
        delivery = delivered + timedelta(days=cover - 1)
        return delivery, delivery - timedelta(days=lead), True
    delivery = today + timedelta(days=1)
    return delivery, today, False
