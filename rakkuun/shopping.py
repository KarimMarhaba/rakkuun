"""Einkaufsliste aus dem Wochenplan: Mengen bündeln, auf Packungen runden,
nach Haltbarkeit auf ein oder zwei Lieferungen aufteilen und den
Mindestbestellwert einhalten."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .data import Catalog


@dataclass
class OrderLine:
    ingredient_id: str
    name: str
    mytime_query: str
    grams_needed: float
    packages: int
    price_eur: float

    @property
    def total_eur(self) -> float:
        return self.packages * self.price_eur


@dataclass
class Delivery:
    day: int
    lines: list[OrderLine] = field(default_factory=list)
    filler: list[OrderLine] = field(default_factory=list)

    @property
    def total_eur(self) -> float:
        return round(sum(line.total_eur for line in self.lines + self.filler), 2)


@dataclass
class ShoppingPlan:
    deliveries: list[Delivery]
    # Zutaten, die bei der gewählten Lieferaufteilung vor dem Verbrauch verderben würden
    spoilage_risks: list[tuple[str, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def daily_demand(catalog: Catalog) -> dict[str, dict[int, float]]:
    """Zutat-ID -> {Tag: Gramm}."""
    demand: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for day, meals in enumerate(catalog.plan):
        for meal in meals:
            for ingredient_id, grams in catalog.recipes[meal.recipe].ingredients.items():
                demand[ingredient_id][day] += grams * meal.servings
    return demand


def _build_delivery(catalog: Catalog, day: int, grams: dict[str, float]) -> Delivery:
    delivery = Delivery(day=day)
    for ingredient_id, needed in sorted(grams.items()):
        ing = catalog.ingredients[ingredient_id]
        delivery.lines.append(OrderLine(
            ingredient_id=ingredient_id,
            name=ing.name,
            mytime_query=ing.mytime_query,
            grams_needed=round(needed, 1),
            packages=math.ceil(needed / ing.package_g),
            price_eur=ing.price_eur,
        ))
    return delivery


def _split(catalog: Catalog, delivery_days: list[int]):
    """Ordnet jeden Tagesbedarf der spätesten Lieferung vor dem Verbrauchstag zu.
    Liefert Gramm je Lieferung und die Bedarfe, die trotzdem verderben würden."""
    per_delivery: list[dict[str, float]] = [defaultdict(float) for _ in delivery_days]
    risks: list[tuple[str, int]] = []
    for ingredient_id, by_day in daily_demand(catalog).items():
        shelf_life = catalog.ingredients[ingredient_id].shelf_life_days
        for day, grams in by_day.items():
            candidates = [i for i, d in enumerate(delivery_days) if d <= day]
            fresh = [i for i in candidates if day - delivery_days[i] < shelf_life]
            # Lange Haltbares immer mit der ersten Lieferung, Frisches so spät wie möglich
            index = fresh[0] if fresh and shelf_life >= 30 else (fresh or candidates)[-1]
            if not fresh:
                risks.append((ingredient_id, day))
            per_delivery[index][ingredient_id] += grams
    return per_delivery, risks


def _fill_to_minimum(catalog: Catalog, delivery: Delivery, minimum: float) -> None:
    """Füllt mit lange haltbaren Vorratsartikeln auf, bis der Mindestbestellwert erreicht ist.
    Bevorzugt Artikel, die ohnehin im Plan vorkommen."""
    used = {line.ingredient_id for line in delivery.lines}
    staples = sorted(
        (ing for ing in catalog.ingredients.values() if ing.staple),
        key=lambda ing: (ing.id not in used, ing.price_eur),
    )
    if not staples:
        return
    i = 0
    while delivery.total_eur < minimum:
        ing = staples[i % len(staples)]
        existing = next((l for l in delivery.filler if l.ingredient_id == ing.id), None)
        if existing:
            existing.packages += 1
        else:
            delivery.filler.append(OrderLine(ing.id, ing.name, ing.mytime_query, 0, 1, ing.price_eur))
        i += 1


def build_shopping_plan(catalog: Catalog) -> ShoppingPlan:
    profile = catalog.profile
    minimum = profile.min_order_eur

    one_grams, one_risks = _split(catalog, [0])
    if profile.max_deliveries_per_week >= 2 and one_risks:
        two_grams, two_risks = _split(catalog, [0, profile.second_delivery_day])
        two = [_build_delivery(catalog, d, g) for d, g in zip([0, profile.second_delivery_day], two_grams)]
        if all(d.total_eur >= minimum for d in two):
            return ShoppingPlan(two, two_risks, [
                f"Zwei Lieferungen (Tag 0 und Tag {profile.second_delivery_day}), "
                "damit frische Zutaten nicht verderben."])
        notes = [
            f"Eine zweite Lieferung würde den Mindestbestellwert von {minimum:.2f} € nicht erreichen "
            f"(Lieferung 2: {two[1].total_eur:.2f} €). Daher nur eine Lieferung – die markierten "
            "Zutaten sollten durch TK- oder länger haltbare Varianten ersetzt oder im Plan nach "
            "vorne verschoben werden."]
    else:
        notes = []

    delivery = _build_delivery(catalog, 0, one_grams[0])
    if delivery.total_eur < minimum:
        before = delivery.total_eur
        _fill_to_minimum(catalog, delivery, minimum)
        notes.append(f"Warenkorb ({before:.2f} €) mit Vorratsartikeln auf den Mindestbestellwert "
                     f"von {minimum:.2f} € aufgefüllt.")
    return ShoppingPlan([delivery], one_risks, notes)
