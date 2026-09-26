from pathlib import Path

import pytest
import yaml

from rakkuun.data import DATA_DIR, load_catalog
from rakkuun.nutrition import day_nutrients
from rakkuun.shopping import build_shopping_plan

PLAN = DATA_DIR / "plans" / "beispiel-woche.yaml"


def _catalog_with(tmp_path: Path, plan_days, **ordering):
    """Kopiert die echten Daten und überschreibt Plan und Bestellregeln."""
    for name in ("ingredients.yaml", "recipes.yaml"):
        (tmp_path / name).write_text((DATA_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    profile = yaml.safe_load((DATA_DIR / "profile.yaml").read_text(encoding="utf-8"))
    profile["ordering"].update(ordering)
    (tmp_path / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    plan = tmp_path / "plan.yaml"
    plan.write_text(yaml.safe_dump({"days": plan_days}), encoding="utf-8")
    return load_catalog(plan, tmp_path)


def test_nutrients_scale_with_grams():
    catalog = load_catalog(PLAN)
    totals = day_nutrients(catalog, catalog.plan[0][:1])  # Overnight Oats
    # 80 g Hafer + 250 g Quark + 100 g Beeren + 100 g Banane
    assert totals["protein"] == pytest.approx(0.8 * 13.5 + 2.5 * 12.0 + 0.6 + 1.2)


def test_packages_are_rounded_up():
    catalog = load_catalog(PLAN)
    lines = {l.ingredient_id: l for d in build_shopping_plan(catalog).deliveries for l in d.lines}
    assert lines["magerquark"].grams_needed == 1750
    assert lines["magerquark"].packages == 4


def test_every_delivery_meets_minimum_order():
    catalog = load_catalog(PLAN)
    for delivery in build_shopping_plan(catalog).deliveries:
        assert delivery.total_eur >= catalog.profile.min_order_eur


def test_small_order_is_filled_with_staples(tmp_path):
    catalog = _catalog_with(tmp_path, [["overnight_oats"]])
    plan = build_shopping_plan(catalog)
    (delivery,) = plan.deliveries
    assert delivery.total_eur >= 70
    assert delivery.filler
    assert all(catalog.ingredients[l.ingredient_id].staple for l in delivery.filler)


def test_two_deliveries_when_both_reach_minimum(tmp_path):
    heavy_day = ["haehnchen_reis_brokkoli"] * 4
    catalog = _catalog_with(tmp_path, [heavy_day] * 7, min_order_eur=40)
    plan = build_shopping_plan(catalog)
    assert [d.day for d in plan.deliveries] == [0, 3]
    assert not plan.spoilage_risks
    # Frisches Hähnchen für Tag 3+ kommt mit der zweiten Lieferung
    second = {l.ingredient_id: l for l in plan.deliveries[1].lines}
    assert second["haehnchenbrust"].grams_needed == 4 * 800
    # Lange Haltbares kommt komplett mit der ersten Lieferung
    first = {l.ingredient_id: l for l in plan.deliveries[0].lines}
    assert first["basmatireis"].grams_needed == 7 * 4 * 90
    assert "basmatireis" not in second


def test_single_delivery_flags_spoilage_when_second_too_small():
    catalog = load_catalog(PLAN)
    plan = build_shopping_plan(catalog)
    assert len(plan.deliveries) == 1
    assert ("haehnchenbrust", 5) in plan.spoilage_risks


def test_unknown_recipe_in_plan_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unbekanntes Rezept"):
        _catalog_with(tmp_path, [["gibt_es_nicht"]])
