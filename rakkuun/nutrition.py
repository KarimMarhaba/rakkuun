"""Nährwertberechnung."""

from __future__ import annotations

from collections import defaultdict

from .data import Catalog
from .plan import Day, day_grams


def nutrients(catalog: Catalog, grams: dict[str, float]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for ingredient_id, amount in grams.items():
        for nutrient, value in catalog.ingredients[ingredient_id].per_100g.items():
            totals[nutrient] += value * amount / 100
    return dict(totals)


def day_nutrients(catalog: Catalog, day: Day) -> dict[str, float]:
    return nutrients(catalog, day_grams(catalog, day))
