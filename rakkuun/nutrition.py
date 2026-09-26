"""Nährwertberechnung und Abgleich mit den Tageszielen."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .data import Catalog, Meal


def meal_nutrients(catalog: Catalog, meal: Meal) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    recipe = catalog.recipes[meal.recipe]
    for ingredient_id, grams in recipe.ingredients.items():
        per_100g = catalog.ingredients[ingredient_id].per_100g
        for nutrient, value in per_100g.items():
            totals[nutrient] += value * grams * meal.servings / 100
    return dict(totals)


def day_nutrients(catalog: Catalog, meals: list[Meal]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for meal in meals:
        for nutrient, value in meal_nutrients(catalog, meal).items():
            totals[nutrient] += value
    return dict(totals)


@dataclass(frozen=True)
class TargetCheck:
    nutrient: str
    actual: float
    target: float
    ok: bool
    is_minimum: bool


def check_day(catalog: Catalog, meals: list[Meal]) -> list[TargetCheck]:
    profile = catalog.profile
    actual = day_nutrients(catalog, meals)
    tolerance = profile.tolerance_pct / 100
    checks = []
    for nutrient, target in profile.daily_targets.items():
        value = actual.get(nutrient, 0.0)
        is_minimum = nutrient in profile.minimum_targets
        if is_minimum:
            ok = value >= target
        else:
            ok = abs(value - target) <= target * tolerance
        checks.append(TargetCheck(nutrient, value, target, ok, is_minimum))
    return checks
