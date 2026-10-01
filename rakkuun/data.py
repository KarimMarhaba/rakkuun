"""Laden und Validieren der YAML-Daten."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


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
    tags: tuple[str, ...] = ()
    kaufregel: str = ""
    mytime: dict = field(default_factory=dict, hash=False, compare=False)  # zugeordnetes MyTime-Produkt

    @property
    def mytime_step(self) -> int:
        return int(self.mytime.get("step", 1))

    @property
    def mytime_status(self) -> str:
        return self.mytime.get("status", "offen")


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    mahlzeit: str
    active_minutes: int
    zero_prep: bool
    ingredients: dict[str, float]  # Zutat-ID -> Gramm pro Portion
    variants: dict[str, dict[str, float]] = field(default_factory=dict)
    anleitung: str = ""


@dataclass
class Catalog:
    ingredients: dict[str, Ingredient]
    recipes: dict[str, Recipe]
    rules: dict[str, Any]
    template: dict[str, Any]
    settings: dict[str, Any]
    preferences: dict[str, Any]
    pantry: dict[str, float]
    weights: dict[str, float]
    data_dir: Path = DATA_DIR

    @property
    def ordering(self) -> dict[str, Any]:
        return self.settings["bestellung"]


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: Any, header: str = "") -> None:
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=True) if data else "{}\n"
    path.write_text(header + body, encoding="utf-8")


def _load_ingredients(path: Path) -> dict[str, Ingredient]:
    result = {}
    for key, value in load_yaml(path).items():
        value = dict(value)
        value["tags"] = tuple(value.get("tags", ()))
        result[key] = Ingredient(id=key, **value)
    return result


def _load_recipes(path: Path, ingredients: dict[str, Ingredient]) -> dict[str, Recipe]:
    recipes = {key: Recipe(id=key, **value) for key, value in load_yaml(path).items()}
    for recipe in recipes.values():
        used = set(recipe.ingredients)
        for overrides in recipe.variants.values():
            used |= set(overrides)
        unknown = used - set(ingredients)
        if unknown:
            raise ValueError(f"Rezept '{recipe.id}' nutzt unbekannte Zutaten: {sorted(unknown)}")
    return recipes


def _check_references(catalog: Catalog) -> None:
    t, p = catalog.template, catalog.preferences
    recipe_refs = (list(t["mahlzeiten"]) + list(t.get("fleisch", {}))
                   + list(t.get("spieltag_extras", [])) + list(t.get("woechentliche_extras", [])))
    unknown = [r for r in recipe_refs if r not in catalog.recipes]
    if unknown:
        raise ValueError(f"Wochenvorlage nutzt unbekannte Rezepte: {unknown}")
    ing_refs = (list(t.get("huelsenfrucht_rotation", [])) + list(p.get("abneigungen", []))
                + list(p.get("tausch", {})) + list(p.get("tausch", {}).values()) + list(catalog.pantry))
    unknown = sorted({i for i in ing_refs if i not in catalog.ingredients})
    if unknown:
        raise ValueError(f"Unbekannte Zutat-IDs in Vorlage/Vorlieben/Vorrat: {unknown}")
    days = catalog.settings["wochentage"]
    if set(days) != set(WEEKDAYS):
        raise ValueError(f"einstellungen.yaml: wochentage muss genau {WEEKDAYS} enthalten")
    if catalog.ordering["liefertag"] not in WEEKDAYS:
        raise ValueError("einstellungen.yaml: unbekannter liefertag")


def load_catalog(data_dir: Path = DATA_DIR) -> Catalog:
    ingredients = _load_ingredients(data_dir / "ingredients.yaml")
    catalog = Catalog(
        ingredients=ingredients,
        recipes=_load_recipes(data_dir / "recipes.yaml", ingredients),
        rules=load_yaml(data_dir / "regeln.yaml"),
        template=load_yaml(data_dir / "wochenvorlage.yaml"),
        settings=load_yaml(data_dir / "einstellungen.yaml"),
        preferences=load_yaml(data_dir / "vorlieben.yaml"),
        pantry={k: float(v) for k, v in load_yaml(data_dir / "vorrat.yaml").items()},
        weights={str(k): float(v) for k, v in load_yaml(data_dir / "gewicht.yaml").items()},
        data_dir=data_dir,
    )
    _check_references(catalog)
    return catalog
