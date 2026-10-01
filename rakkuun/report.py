"""Markdown-Bericht: Wochenplan, Regelprüfung und Bestellvorschlag."""

from __future__ import annotations

from .data import Catalog
from .nutrition import day_nutrients
from .plan import Week
from .rules import LABELS, Finding, current_weight
from .shopping import ShoppingPlan

COLUMNS = ["kcal", "protein", "carbs", "fat", "fiber", "calcium_mg", "iron_mg", "magnesium_mg", "zinc_mg"]


def merge_daily(findings: list[Finding], days: int = 7) -> list[Finding]:
    """Gleicher Befund an allen Tagen -> einmal als 'Täglich'."""
    count: dict[tuple, int] = {}
    for f in findings:
        count[(f.stufe, f.text, f.grund)] = count.get((f.stufe, f.text, f.grund), 0) + 1
    merged, seen = [], set()
    for f in findings:
        key = (f.stufe, f.text, f.grund)
        if count[key] >= days:
            if key not in seen:
                merged.append(Finding(f.stufe, "Täglich", f.text, f.grund))
                seen.add(key)
        else:
            merged.append(f)
    return merged


def render_findings(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["✅ Alle Grundregeln eingehalten."]
    out = []
    for f in sorted(merge_daily(findings), key=lambda f: (not f.is_error, f.wo)):
        icon = "❌" if f.is_error else "💡"
        out.append(f"- {icon} **{f.wo}:** {f.text}" + (f" – _{f.grund}_" if f.grund else ""))
    return out


def render(catalog: Catalog, week: Week, findings: list[Finding], shopping: ShoppingPlan | None) -> str:
    legume = catalog.ingredients[week.legume].name if week.legume else "–"
    out = [f"# Wochenplan KW {week.iso_week}", "",
           f"Gewicht: {current_weight(catalog):.1f} kg · Hülsenfrucht der Woche: {legume}", "",
           "| Tag | Typ | Extras | " + " | ".join(LABELS[c][0] for c in COLUMNS) + " |",
           "|---|---|---|" + "---|" * len(COLUMNS)]
    base = set(catalog.template["mahlzeiten"])
    for day in week.days:
        values = day_nutrients(catalog, day)
        extras = ", ".join(catalog.recipes[m].name.split(" (")[0] for m in day.meals if m not in base)
        typ = day.typ + (" · Spiel" if day.game_day else "")
        out.append(f"| {day.weekday} | {typ} | {extras} | "
                   + " | ".join(f"{values.get(c, 0):.0f}" for c in COLUMNS) + " |")
    out += ["", "Täglich: " + ", ".join(catalog.recipes[m].name for m in catalog.template["mahlzeiten"]), ""]

    out += ["## Regelprüfung", *render_findings(findings), ""]
    habits = catalog.rules.get("gewohnheiten") or []
    if habits:
        out += ["## Nicht vergessen", *[f"- {h}" for h in habits], ""]

    if shopping is None:
        out.append("_Kein Bestellvorschlag, weil der Plan gegen Grundregeln verstößt._")
        return "\n".join(out) + "\n"

    out.append("## Bestellvorschlag MyTime")
    out += [f"> {note}" for note in shopping.notes]
    for i, delivery in enumerate(shopping.deliveries, 1):
        out += ["", f"### Lieferung {i} (Tag {delivery.day}) – {delivery.total_eur:.2f} €", "",
                "| Artikel | Bedarf | Packungen | Preis | Worauf achten |", "|---|---|---|---|---|"]
        for line in delivery.lines:
            out.append(f"| {line.name} | {line.grams_needed:.0f} g | {line.packages} | "
                       f"{line.total_eur:.2f} € | {line.kaufregel} |")
        for line in delivery.filler:
            out.append(f"| {line.name} _(Vorrat)_ | – | {line.packages} | {line.total_eur:.2f} € | {line.kaufregel} |")
    if shopping.buy_locally:
        out += ["", "### 🛒 Vor Ort kaufen (bei Bedarf)"]
        for ingredient_id, grams in shopping.buy_locally.items():
            out.append(f"- {catalog.ingredients[ingredient_id].name}: ca. {grams} g für die letzten Tage der Woche")
    if shopping.spoilage_risks:
        out += ["", "### Zuerst verbrauchen / zu reif → anders verwerten"]
        by_ingredient: dict[str, list[str]] = {}
        for ingredient_id, day in sorted(shopping.spoilage_risks, key=lambda r: (r[1], r[0])):
            by_ingredient.setdefault(ingredient_id, []).append(week.days[day].weekday)
        for ingredient_id, weekdays in by_ingredient.items():
            out.append(f"- {catalog.ingredients[ingredient_id].name}: ab {weekdays[0]} evtl. sehr reif "
                       "(z. B. eingefroren ins Oatmeal)")
    if catalog.ordering.get("bestaetigung_erforderlich", True):
        out += ["", "_Bestellung wird erst nach deiner Bestätigung abgeschickt._"]
    return "\n".join(out) + "\n"
