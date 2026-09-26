"""Markdown-Bericht: Nährwerte pro Tag und Bestellvorschlag zur Bestätigung."""

from __future__ import annotations

from .data import Catalog
from .nutrition import check_day
from .shopping import ShoppingPlan

UNITS = {"kcal": "kcal", "calcium_mg": "mg", "iron_mg": "mg", "magnesium_mg": "mg"}


def _fmt(nutrient: str, value: float) -> str:
    return f"{value:.0f} {UNITS.get(nutrient, 'g')}"


def render(catalog: Catalog, shopping: ShoppingPlan) -> str:
    out = ["# Wochenplan", ""]
    nutrients = list(catalog.profile.daily_targets)
    out.append("| Tag | Gerichte | " + " | ".join(nutrients) + " |")
    out.append("|---|---|" + "---|" * len(nutrients))
    for day, meals in enumerate(catalog.plan):
        dishes = ", ".join(catalog.recipes[m.recipe].name for m in meals)
        cells = [("✅ " if c.ok else "⚠️ ") + _fmt(c.nutrient, c.actual) for c in check_day(catalog, meals)]
        out.append(f"| {day} | {dishes} | " + " | ".join(cells) + " |")
    targets = ", ".join(
        f"{n} {'≥' if n in catalog.profile.minimum_targets else '≈'} {_fmt(n, t)}"
        for n, t in catalog.profile.daily_targets.items())
    out += ["", f"Ziele: {targets}", ""]

    out.append("# Bestellvorschlag MyTime")
    for note in shopping.notes:
        out.append(f"> {note}")
    for i, delivery in enumerate(shopping.deliveries, 1):
        out += ["", f"## Lieferung {i} (Tag {delivery.day}) – {delivery.total_eur:.2f} €", "",
                "| Artikel | Bedarf | Packungen | Preis |", "|---|---|---|---|"]
        for line in delivery.lines:
            out.append(f"| {line.name} | {line.grams_needed:.0f} g | {line.packages} | {line.total_eur:.2f} € |")
        for line in delivery.filler:
            out.append(f"| {line.name} *(Vorrat)* | – | {line.packages} | {line.total_eur:.2f} € |")
    if shopping.spoilage_risks:
        out += ["", "## ⚠️ Haltbarkeit"]
        for ingredient_id, day in sorted(shopping.spoilage_risks, key=lambda r: (r[1], r[0])):
            out.append(f"- {catalog.ingredients[ingredient_id].name}: an Tag {day} vermutlich nicht mehr frisch")
    if catalog.profile.require_confirmation:
        out += ["", "_Bestellung wird erst nach deiner Bestätigung abgeschickt._"]
    return "\n".join(out) + "\n"
