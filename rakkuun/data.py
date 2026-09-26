"""Laden und Validieren der YAML-Daten (Zutaten, Rezepte, Profil, Wochenplan)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Ingredient:
    id: str
    name: str
    mytime_query: str
    package_g: float
    price_eur: float
    shelf_life_days: int
    per_100g: dict[str, float]
    staple: bool = False


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    prep_minutes: int
    ingredients: dict[str, float]  # Zutat-ID -> Gramm pro Portion


@dataclass(frozen=True)
class Meal:
    recipe: str
    servings: float = 1.0


@dataclass
class Profile:
    daily_targets: dict[str, float]
    minimum_targets: list[str]
    tolerance_pct: float
    min_order_eur: float
    max_deliveries_per_week: int
    second_delivery_day: int
    require_confirmation: bool = True


@dataclass
class Catalog:
    ingredients: dict[str, Ingredient]
    recipes: dict[str, Recipe]
    profile: Profile
    plan: list[list[Meal]] = field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_ingredients(path: Path) -> dict[str, Ingredient]:
    return {key: Ingredient(id=key, **value) for key, value in _load_yaml(path).items()}


def load_recipes(path: Path, ingredients: dict[str, Ingredient]) -> dict[str, Recipe]:
    recipes = {key: Recipe(id=key, **value) for key, value in _load_yaml(path).items()}
    for recipe in recipes.values():
        unknown = set(recipe.ingredients) - set(ingredients)
        if unknown:
            raise ValueError(f"Rezept '{recipe.id}' nutzt unbekannte Zutaten: {sorted(unknown)}")
    return recipes


def load_profile(path: Path) -> Profile:
    raw = _load_yaml(path)
    return Profile(
        daily_targets=raw["daily_targets"],
        minimum_targets=raw.get("minimum_targets", []),
        tolerance_pct=raw.get("tolerance_pct", 10),
        **raw["ordering"],
    )


def load_plan(path: Path, recipes: dict[str, Recipe]) -> list[list[Meal]]:
    days = []
    for day in _load_yaml(path)["days"]:
        meals = []
        for entry in day:
            meal = Meal(recipe=entry) if isinstance(entry, str) else Meal(**entry)
            if meal.recipe not in recipes:
                raise ValueError(f"Unbekanntes Rezept im Plan: '{meal.recipe}'")
            meals.append(meal)
        days.append(meals)
    return days


def load_catalog(plan_path: Path | None = None, data_dir: Path = DATA_DIR) -> Catalog:
    ingredients = load_ingredients(data_dir / "ingredients.yaml")
    recipes = load_recipes(data_dir / "recipes.yaml", ingredients)
    catalog = Catalog(ingredients, recipes, load_profile(data_dir / "profile.yaml"))
    if plan_path is not None:
        catalog.plan = load_plan(plan_path, recipes)
    return catalog
