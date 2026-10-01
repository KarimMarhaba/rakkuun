"""Wochenplan aus der Vorlage erzeugen und in Zutatenmengen auflösen."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .data import WEEKDAYS, Catalog


@dataclass
class Day:
    index: int            # 0 = Liefertag
    weekday: str
    typ: str              # training | leicht
    game_day: bool
    meals: list[str]
    swaps: dict[str, str] = field(default_factory=dict)


@dataclass
class Week:
    iso_week: int
    days: list[Day]
    legume: str


def generate_week(catalog: Catalog, iso_week: int) -> Week:
    template, settings = catalog.template, catalog.settings
    start = WEEKDAYS.index(catalog.ordering["liefertag"])
    weekdays = WEEKDAYS[start:] + WEEKDAYS[:start]
    game_days = set(settings.get("spieltage", []))

    rotation = template.get("huelsenfrucht_rotation") or []
    legume = rotation[iso_week % len(rotation)] if rotation else ""
    swaps = dict(catalog.preferences.get("tausch") or {})
    if legume and legume != "kichererbsen":
        swaps.setdefault("kichererbsen", legume)

    # Fleisch verteilen: salzig Mariniertes zuerst auf Spieltage (Natriumverlust), dann Trainingstage
    meat_by_day: dict[str, str] = {}
    priority = sorted(weekdays, key=lambda d: (d not in game_days, settings["wochentage"][d] != "training"))
    remaining = [d for d in priority]

    def salty(recipe_id: str) -> bool:
        return any("mariniert_salzig" in catalog.ingredients[i].tags
                   for i in catalog.recipes[recipe_id].ingredients)

    meats = sorted((template.get("fleisch") or {}).items(), key=lambda item: not salty(item[0]))
    for recipe_id, count in meats:
        for weekday in remaining[:count]:
            meat_by_day[weekday] = recipe_id
        remaining = remaining[count:]

    days = []
    for index, weekday in enumerate(weekdays):
        meals = list(template["mahlzeiten"])
        if weekday in meat_by_day:
            meals.append(meat_by_day[weekday])
        if weekday in game_days:
            meals += template.get("spieltag_extras", [])
        if index == 0:
            meals += template.get("woechentliche_extras", [])
        days.append(Day(index, weekday, settings["wochentage"][weekday], weekday in game_days, meals, swaps))
    return Week(iso_week, days, legume)


def meal_grams(catalog: Catalog, recipe_id: str, day: Day) -> dict[str, float]:
    recipe = catalog.recipes[recipe_id]
    grams = dict(recipe.ingredients)
    grams.update(recipe.variants.get(day.typ, {}))
    result: dict[str, float] = defaultdict(float)
    for ingredient_id, amount in grams.items():
        result[day.swaps.get(ingredient_id, ingredient_id)] += amount
    return dict(result)


def day_grams(catalog: Catalog, day: Day) -> dict[str, float]:
    total: dict[str, float] = defaultdict(float)
    for recipe_id in day.meals:
        for ingredient_id, amount in meal_grams(catalog, recipe_id, day).items():
            total[ingredient_id] += amount
    return dict(total)
