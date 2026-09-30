"""Einkaufsliste aus dem Wochenplan: Vorrat abziehen, auf Packungen runden,
nach Haltbarkeit auf ein oder zwei Lieferungen aufteilen und den
Mindestbestellwert einhalten."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .data import Catalog
from .plan import Week, day_grams

LONG_LIFE_DAYS = 30  # ab hier kommt eine Zutat immer mit der ersten Lieferung


@dataclass
class OrderLine:
    ingredient_id: str
    name: str
    mytime_query: str
    grams_needed: float
    packages: int
    price_eur: float
    kaufregel: str = ""

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
    # (Zutat-ID, Tag): Bedarf, der bei der gewählten Aufteilung nicht mehr frisch wäre
    spoilage_risks: list[tuple[str, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pantry_after: dict[str, float] = field(default_factory=dict)


def daily_demand(catalog: Catalog, week: Week) -> dict[str, dict[int, float]]:
    """Zutat-ID -> {Tag: Gramm}, nach Abzug des Vorrats (älteste Tage zuerst)."""
    demand: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for day in week.days:
        for ingredient_id, grams in day_grams(catalog, day).items():
            demand[ingredient_id][day.index] += grams
    for ingredient_id, stock in catalog.pantry.items():
        for day in sorted(demand.get(ingredient_id, {})):
            used = min(stock, demand[ingredient_id][day])
            demand[ingredient_id][day] -= used
            stock -= used
    return {i: {d: g for d, g in by_day.items() if g > 0} for i, by_day in demand.items()}


def _line(catalog: Catalog, ingredient_id: str, grams: float, packages: int) -> OrderLine:
    ing = catalog.ingredients[ingredient_id]
    return OrderLine(ingredient_id, ing.name, ing.mytime_query, round(grams, 1), packages,
                     ing.price_eur, ing.kaufregel)


def _build_delivery(catalog: Catalog, day: int, grams: dict[str, float]) -> Delivery:
    delivery = Delivery(day=day)
    for ingredient_id, needed in sorted(grams.items()):
        if needed > 0:
            packages = math.ceil(needed / catalog.ingredients[ingredient_id].package_g - 1e-9)
            delivery.lines.append(_line(catalog, ingredient_id, needed, packages))
    return delivery


def _split(catalog: Catalog, demand: dict[str, dict[int, float]], delivery_days: list[int]):
    """Ordnet jeden Tagesbedarf einer Lieferung zu: lange Haltbares immer der ersten,
    Frisches der spätesten Lieferung vor dem Verbrauchstag."""
    per_delivery: list[dict[str, float]] = [defaultdict(float) for _ in delivery_days]
    risks: list[tuple[str, int]] = []
    for ingredient_id, by_day in demand.items():
        shelf_life = catalog.ingredients[ingredient_id].shelf_life_days
        for day, grams in by_day.items():
            candidates = [i for i, d in enumerate(delivery_days) if d <= day]
            fresh = [i for i in candidates if day - delivery_days[i] < shelf_life]
            if shelf_life >= LONG_LIFE_DAYS and fresh:
                index = fresh[0]
            else:
                index = (fresh or candidates)[-1]
            if not fresh:
                risks.append((ingredient_id, day))
            per_delivery[index][ingredient_id] += grams
    return per_delivery, risks


def _fill_to_minimum(catalog: Catalog, week: Week, delivery: Delivery, minimum: float) -> None:
    """Füllt mit lange haltbaren Vorratsartikeln auf, bis der Mindestbestellwert erreicht ist.
    Bevorzugt, was im Plan am schnellsten verbraucht wird – das ist dann Vorrat für die nächsten Wochen."""
    weekly: dict[str, float] = defaultdict(float)
    for day in week.days:
        for ingredient_id, grams in day_grams(catalog, day).items():
            weekly[ingredient_id] += grams
    dislikes = set(catalog.preferences.get("abneigungen") or [])
    staples = [ing for ing in catalog.ingredients.values()
               if ing.staple and weekly.get(ing.id) and ing.id not in dislikes]
    staples.sort(key=lambda ing: -weekly[ing.id] / ing.package_g)
    if not staples:
        return
    i = 0
    while delivery.total_eur < minimum:
        ing = staples[i % len(staples)]
        existing = next((l for l in delivery.filler if l.ingredient_id == ing.id), None)
        if existing:
            existing.packages += 1
        else:
            delivery.filler.append(_line(catalog, ing.id, 0, 1))
        i += 1


def _pantry_after(catalog: Catalog, week: Week, deliveries: list[Delivery]) -> dict[str, float]:
    """Voraussichtlicher Vorrat nach der Woche – nur lange Haltbares wird mitgenommen."""
    stock: dict[str, float] = defaultdict(float, catalog.pantry)
    for delivery in deliveries:
        for line in delivery.lines + delivery.filler:
            stock[line.ingredient_id] += line.packages * catalog.ingredients[line.ingredient_id].package_g
    for day in week.days:
        for ingredient_id, grams in day_grams(catalog, day).items():
            stock[ingredient_id] -= grams
    return {i: round(g) for i, g in sorted(stock.items())
            if g >= 1 and catalog.ingredients[i].shelf_life_days >= LONG_LIFE_DAYS}


def build_shopping_plan(catalog: Catalog, week: Week) -> ShoppingPlan:
    ordering = catalog.ordering
    minimum = ordering["mindestbestellwert_eur"]
    second_day = ordering["zweite_lieferung_nach_tagen"]
    demand = daily_demand(catalog, week)

    one_grams, one_risks = _split(catalog, demand, [0])
    notes: list[str] = []
    if ordering["max_lieferungen_pro_woche"] >= 2 and one_risks:
        two_grams, two_risks = _split(catalog, demand, [0, second_day])
        two = [_build_delivery(catalog, d, g) for d, g in zip([0, second_day], two_grams)]
        if all(d.total_eur >= minimum for d in two):
            plan = ShoppingPlan(two, two_risks, [
                f"Zwei Lieferungen (Tag 0 und Tag {second_day}), damit Frisches nicht verdirbt."])
            plan.pantry_after = _pantry_after(catalog, week, two)
            return plan
        notes.append(
            f"Eine zweite Lieferung käme nur auf {two[1].total_eur:.2f} € und damit unter den "
            f"Mindestbestellwert von {minimum:.2f} € – deshalb eine Lieferung. Die unten markierten "
            "Zutaten zuerst verbrauchen oder rechtzeitig einfrieren.")

    delivery = _build_delivery(catalog, 0, one_grams[0])
    if delivery.total_eur < minimum:
        before = delivery.total_eur
        _fill_to_minimum(catalog, week, delivery, minimum)
        notes.append(f"Warenkorb ({before:.2f} €) mit Vorrat für die nächste Woche auf den "
                     f"Mindestbestellwert von {minimum:.2f} € aufgefüllt.")
    plan = ShoppingPlan([delivery], one_risks, notes)
    plan.pantry_after = _pantry_after(catalog, week, [delivery])
    return plan
