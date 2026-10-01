"""Prüft einen Wochenplan gegen die Grundregeln (regeln.yaml) und die Vorlieben.

Das ist die Instanz, die sicherstellt, dass Anpassungen an Vorlieben nie
still und leise eine Grundregel aushebeln: Jeder Plan läuft hier durch, und
ein Plan mit Fehlern wird weder gespeichert noch bestellt."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .data import Catalog
from .nutrition import day_nutrients
from .plan import Week, day_grams

LABELS = {
    "kcal": ("Kalorien", "kcal"), "protein": ("Protein", "g"), "carbs": ("Kohlenhydrate", "g"),
    "fat": ("Fett", "g"), "fiber": ("Ballaststoffe", "g"), "calcium_mg": ("Calcium", "mg"),
    "iron_mg": ("Eisen", "mg"), "magnesium_mg": ("Magnesium", "mg"), "zinc_mg": ("Zink", "mg"),
    "vitamin_a_ug": ("Vitamin A", "µg"), "vitamin_c_mg": ("Vitamin C", "mg"), "vitamin_d_ug": ("Vitamin D", "µg"),
    "vitamin_b12_ug": ("Vitamin B12", "µg"), "folat_ug": ("Folat", "µg"), "selen_ug": ("Selen", "µg"),
    "kalium_mg": ("Kalium", "mg"), "jod_ug": ("Jod", "µg"), "omega3_epa_dha_mg": ("Omega-3 EPA/DHA", "mg"),
}

FOOD = "nahrung"  # Regeln mit anderer 'quelle' (supplement, jodsalz) werden nicht gegen das Essen geprüft


def food_rules(rules: dict) -> list[dict]:
    return [r for r in rules.get("naehrwerte", []) if r.get("quelle", FOOD) == FOOD]


@dataclass(frozen=True)
class Finding:
    stufe: str      # fehler | hinweis
    wo: str         # z. B. "Mo" oder "Woche"
    text: str
    grund: str = ""

    @property
    def is_error(self) -> bool:
        return self.stufe == "fehler"


def current_weight(catalog: Catalog) -> float:
    if catalog.weights:
        return catalog.weights[max(catalog.weights)]
    return float(catalog.rules["koerpergewicht_kg"])


def weight_trend_kg_per_month(catalog: Catalog) -> float | None:
    """Zunahme pro Monat über den Zeitraum der Kalorien-Regel (lineare Regression)."""
    weeks = catalog.rules.get("kalorien_regel", {}).get("zeitraum_wochen", 4)
    points = sorted((date.fromisoformat(d), kg) for d, kg in catalog.weights.items())
    if len(points) < 2 or (points[-1][0] - points[0][0]).days < weeks * 7:
        return None
    cutoff = points[-1][0].toordinal() - weeks * 7
    points = [(d.toordinal(), kg) for d, kg in points if d.toordinal() >= cutoff]
    if len(points) < 2:
        return None
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    var = sum((x - mean_x) ** 2 for x, _ in points)
    slope_per_day = sum((x - mean_x) * (y - mean_y) for x, y in points) / var
    return slope_per_day * 30.4


def _bounds(rule: dict, weight: float) -> tuple[float | None, float | None]:
    lo = rule.get("min", rule["min_pro_kg"] * weight if "min_pro_kg" in rule else None)
    hi = rule.get("max", rule["max_pro_kg"] * weight if "max_pro_kg" in rule else None)
    return lo, hi


def _fmt(nutrient: str, value: float) -> str:
    label, unit = LABELS.get(nutrient, (nutrient, ""))
    digits = 1 if unit == "g" or abs(value) < 10 else 0
    return f"{label} {value:.{digits}f} {unit}".strip()


def validate(catalog: Catalog, week: Week) -> list[Finding]:
    rules = catalog.rules
    weight = current_weight(catalog)
    findings: list[Finding] = []
    dislikes = set(catalog.preferences.get("abneigungen") or [])
    everyday = rules.get("alltag", {})
    weekly_tags: dict[str, float] = defaultdict(float)

    for day in week.days:
        grams = day_grams(catalog, day)
        values = day_nutrients(catalog, day)

        for rule in food_rules(rules):
            if rule.get("tagestyp") not in (None, day.typ):
                continue
            nutrient = rule["naehrstoff"]
            value = values.get(nutrient, 0.0)
            lo, hi = _bounds(rule, weight)
            if lo is not None and value < lo:
                findings.append(Finding(rule["stufe"], day.weekday,
                                        f"{_fmt(nutrient, value)} < Minimum {lo:.0f}", rule.get("grund", "")))
            if hi is not None and value > hi:
                findings.append(Finding(rule["stufe"], day.weekday,
                                        f"{_fmt(nutrient, value)} > Maximum {hi:.0f}", rule.get("grund", "")))

        tag_grams: dict[str, float] = defaultdict(float)
        for ingredient_id, amount in grams.items():
            for tag in catalog.ingredients[ingredient_id].tags:
                tag_grams[tag] += amount
                weekly_tags[tag] += amount
        for rule in rules.get("gruppen", []):
            tag, amount = rule["tag"], tag_grams.get(rule["tag"], 0.0)
            if "min_pro_tag_g" in rule and amount < rule["min_pro_tag_g"]:
                findings.append(Finding(rule["stufe"], day.weekday,
                                        f"Gruppe '{tag}': {amount:.0f} g < {rule['min_pro_tag_g']} g",
                                        rule.get("grund", "")))
            if "max_pro_tag_g" in rule and amount > rule["max_pro_tag_g"]:
                findings.append(Finding(rule["stufe"], day.weekday,
                                        f"Gruppe '{tag}': {amount:.0f} g > {rule['max_pro_tag_g']} g",
                                        rule.get("grund", "")))

        minutes = sum(catalog.recipes[r].active_minutes for r in day.meals)
        limit = everyday.get("max_aktive_minuten_pro_tag")
        if limit is not None and minutes > limit:
            findings.append(Finding("fehler", day.weekday, f"{minutes} Min aktive Handarbeit > {limit} Min",
                                    "Schnelle Gerichte ohne viel Aufwand."))
        if everyday.get("nur_zero_prep"):
            for recipe_id in day.meals:
                if not catalog.recipes[recipe_id].zero_prep:
                    findings.append(Finding("fehler", day.weekday,
                                            f"'{catalog.recipes[recipe_id].name}' ist nicht Zero-Prep",
                                            "Nichts schneiden, nichts vorbereiten."))

        for ingredient_id in sorted(set(grams) & dislikes):
            findings.append(Finding("fehler", day.weekday,
                                    f"Enthält '{catalog.ingredients[ingredient_id].name}' (steht auf deiner Abneigungsliste)",
                                    "Deine Vorlieben."))

    for rule in rules.get("gruppen", []):
        tag, amount = rule["tag"], weekly_tags.get(rule["tag"], 0.0)
        if "min_pro_woche_g" in rule and amount < rule["min_pro_woche_g"]:
            findings.append(Finding(rule["stufe"], "Woche",
                                    f"Gruppe '{tag}': {amount:.0f} g < {rule['min_pro_woche_g']} g",
                                    rule.get("grund", "")))
        if "max_pro_woche_g" in rule and amount > rule["max_pro_woche_g"]:
            findings.append(Finding(rule["stufe"], "Woche",
                                    f"Gruppe '{tag}': {amount:.0f} g > {rule['max_pro_woche_g']} g",
                                    rule.get("grund", "")))

    if catalog.preferences.get("jeden_tag_gleich"):
        first = week.days[0]
        for day in week.days[1:]:
            if day_grams(catalog, day) != day_grams(catalog, first):
                findings.append(Finding("fehler", day.weekday,
                                        f"Weicht von {first.weekday} ab – jeder Tag soll gleich sein",
                                        "Deine Vorlieben: ein Tagesplan für die ganze Woche."))

    trend = weight_trend_kg_per_month(catalog)
    if trend is not None:
        k = rules["kalorien_regel"]
        if trend > k["max_zunahme_kg_pro_monat"]:
            findings.append(Finding("hinweis", "Gewicht",
                                    f"+{trend:.2f} kg/Monat – Überschuss zu groß",
                                    "Stellschrauben 'gewicht_steigt_zu_schnell' anwenden."))
        elif trend < k["min_zunahme_kg_pro_monat"]:
            findings.append(Finding("hinweis", "Gewicht",
                                    f"{trend:+.2f} kg/Monat – Gewicht steigt nicht",
                                    "Nächste Stufe aus 'gewicht_steigt_nicht' anwenden."))
    return findings
