import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from rakkuun.data import DATA_DIR, load_catalog
from rakkuun.nutrition import day_nutrients
from rakkuun.plan import day_grams, generate_week
from rakkuun.rules import validate, weight_trend_kg_per_month
from rakkuun.shopping import build_shopping_plan

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def data(tmp_path):
    """Kopie der echten Daten, die ein Test gefahrlos verändern kann."""
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    return target


def edit(data: Path, name: str, **changes):
    path = data / name
    content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    content.update(changes)
    path.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")


def errors(catalog, kw=0):
    return [f for f in validate(catalog, generate_week(catalog, kw)) if f.is_error]


# --- Der echte Plan ----------------------------------------------------------

@pytest.mark.parametrize("kw", range(4))
def test_real_plan_meets_all_ground_rules(kw):
    catalog = load_catalog()
    assert errors(catalog, kw) == []


def test_oatmeal_matches_plan_v6():
    catalog = load_catalog()
    day = generate_week(catalog, 0).days[0]
    from rakkuun.nutrition import nutrients
    from rakkuun.plan import meal_grams
    values = nutrients(catalog, meal_grams(catalog, "oatmeal", day))
    assert values["kcal"] == pytest.approx(960, rel=0.05)
    assert values["protein"] == pytest.approx(54, rel=0.05)


def varied_week(data):
    """Alte Variante mit Basketball: Spieltage, leichte Tage, Fleisch-Rotation."""
    edit(data, "einstellungen.yaml", spieltage=["Di", "Sa"],
         wochentage={"Mo": "training", "Di": "training", "Mi": "training", "Do": "leicht",
                     "Fr": "training", "Sa": "training", "So": "leicht"})
    edit(data, "wochenvorlage.yaml", fleisch={"fleisch_gyros": 4, "fleisch_brust": 3})
    edit(data, "vorlieben.yaml", jeden_tag_gleich=False)
    return load_catalog(data)


def test_default_plan_is_identical_every_day():
    catalog = load_catalog()
    week = generate_week(catalog, 0)
    first = day_grams(catalog, week.days[0])
    assert all(day_grams(catalog, d) == first for d in week.days)


def test_varying_days_break_same_every_day_preference(data):
    edit(data, "wochenvorlage.yaml", fleisch={"fleisch_gyros": 4, "fleisch_brust": 3})
    assert any("jeder Tag soll gleich sein" in f.text for f in errors(load_catalog(data)))


def test_light_days_use_smaller_portions(data):
    catalog = varied_week(data)
    assert errors(catalog) == []
    days = {d.weekday: d for d in generate_week(catalog, 0).days}
    assert day_grams(catalog, days["Do"])["nudeln"] == 150
    assert day_grams(catalog, days["Mo"])["nudeln"] == 200
    assert day_nutrients(catalog, days["Do"])["kcal"] < day_nutrients(catalog, days["Mo"])["kcal"]


def test_meat_rotation_puts_gyros_on_game_days_and_limits_it(data):
    catalog = varied_week(data)
    week = generate_week(catalog, 0)
    gyros_days = [d.weekday for d in week.days if "fleisch_gyros" in d.meals]
    assert len(gyros_days) == 4
    assert {"Di", "Sa"} <= set(gyros_days)
    assert all("rote_bete_shot" in d.meals for d in week.days if d.game_day)


def test_legume_rotates_weekly():
    catalog = load_catalog()
    legumes = {generate_week(catalog, kw).legume for kw in range(4)}
    assert legumes == {"kichererbsen", "kidneybohnen", "weisse_bohnen", "linsen"}
    week = generate_week(catalog, 1)
    assert "linsen" in day_grams(catalog, week.days[0]) or "kidneybohnen" in day_grams(catalog, week.days[0])
    assert "kichererbsen" not in day_grams(catalog, week.days[0])


# --- Vorlieben dürfen Grundregeln nicht aushebeln ---------------------------

def test_disliked_ingredient_in_plan_is_an_error(data):
    edit(data, "vorlieben.yaml", abneigungen=["tk_brokkoli"])
    found = errors(load_catalog(data))
    assert any("Abneigungsliste" in f.text for f in found)


def test_valid_swap_satisfies_preference_and_rules(data):
    edit(data, "vorlieben.yaml", abneigungen=["tk_brokkoli"], tausch={"tk_brokkoli": "tk_spinat"})
    catalog = load_catalog(data)
    assert errors(catalog) == []
    assert "tk_brokkoli" not in day_grams(catalog, generate_week(catalog, 0).days[0])


def test_dropping_berries_breaks_vitamin_c_rule(data):
    """'Ich mag keine Beeren' darf nicht still Vitamin C streichen."""
    template = yaml.safe_load((data / "wochenvorlage.yaml").read_text(encoding="utf-8"))
    template["mahlzeiten"] = ["oatmeal", "nudeln_tomate_huelsen", "reis_bowl", "skyr_snack"]
    recipes = yaml.safe_load((data / "recipes.yaml").read_text(encoding="utf-8"))
    recipes["skyr_snack"]["ingredients"].pop("tk_beeren")
    (data / "recipes.yaml").write_text(yaml.safe_dump(recipes, allow_unicode=True), encoding="utf-8")
    (data / "wochenvorlage.yaml").write_text(yaml.safe_dump(template, allow_unicode=True), encoding="utf-8")
    assert any("rohes_obst" in f.text for f in errors(load_catalog(data)))


def test_too_much_gyros_breaks_salt_rule(data):
    edit(data, "wochenvorlage.yaml", fleisch={"fleisch_gyros": 7})
    assert any("mariniert_salzig" in f.text for f in errors(load_catalog(data)))


def test_protein_minimum_scales_with_logged_weight(data):
    edit(data, "gewicht.yaml", **{"2026-09-01": 90.0})
    assert any(f.text.startswith("Protein") for f in errors(load_catalog(data)))


def test_weight_trend(data):
    edit(data, "gewicht.yaml", **{"2026-09-01": 65.0, "2026-09-08": 65.3,
                                  "2026-09-15": 65.6, "2026-09-22": 65.9, "2026-09-29": 66.2})
    catalog = load_catalog(data)
    assert weight_trend_kg_per_month(catalog) == pytest.approx(1.3, abs=0.05)
    hints = [f for f in validate(catalog, generate_week(catalog, 0)) if f.wo == "Gewicht"]
    assert hints and "zu groß" in hints[0].text


def test_unknown_references_are_rejected(data):
    edit(data, "vorlieben.yaml", abneigungen=["gibt_es_nicht"])
    with pytest.raises(ValueError, match="Unbekannte Zutat"):
        load_catalog(data)


# --- Einkauf -----------------------------------------------------------------

def test_single_delivery_and_late_bananas_bought_locally():
    catalog = load_catalog()
    shopping = build_shopping_plan(catalog, generate_week(catalog, 0))
    assert len(shopping.deliveries) == 1
    assert not shopping.spoilage_risks
    # Liefertag Mo, Bananen halten 5 Tage -> Sa + So vor Ort
    assert shopping.buy_locally == {"banane": 240}
    line = next(l for l in shopping.deliveries[0].lines if l.ingredient_id == "banane")
    assert line.grams_needed == 600


def test_every_delivery_meets_minimum_order():
    catalog = load_catalog()
    for delivery in build_shopping_plan(catalog, generate_week(catalog, 0)).deliveries:
        assert delivery.total_eur >= catalog.ordering["mindestbestellwert_eur"]


def test_packages_rounded_up_and_pantry_carried_over():
    catalog = load_catalog()
    shopping = build_shopping_plan(catalog, generate_week(catalog, 0))
    lines = {l.ingredient_id: l for d in shopping.deliveries for l in d.lines}
    assert lines["griech_joghurt_10"].grams_needed == 1400
    assert lines["griech_joghurt_10"].packages == 3
    # 1 kg Reis gekauft, 700 g verbraucht -> Rest landet im Vorrat
    assert shopping.pantry_after["basmatireis"] == 300
    # Frisches (Joghurt, 21 Tage) wird nicht als Vorrat fortgeschrieben
    assert "griech_joghurt_10" not in shopping.pantry_after


def test_pantry_reduces_order(data):
    edit(data, "vorrat.yaml", basmatireis=1000, olivenoel=460)
    catalog = load_catalog(data)
    lines = {l.ingredient_id for d in build_shopping_plan(catalog, generate_week(catalog, 0)).deliveries
             for l in d.lines}
    assert "basmatireis" not in lines and "olivenoel" not in lines


def test_small_order_filled_with_plan_staples(data):
    stock = {i: 5000 for i in yaml.safe_load((data / "ingredients.yaml").read_text(encoding="utf-8"))}
    stock.pop("banane")
    edit(data, "vorrat.yaml", **stock)
    catalog = load_catalog(data)
    (delivery,) = build_shopping_plan(catalog, generate_week(catalog, 0)).deliveries
    assert delivery.total_eur >= 70
    assert delivery.filler and all(catalog.ingredients[l.ingredient_id].staple for l in delivery.filler)


def test_two_deliveries_when_both_reach_minimum(data):
    edit(data, "einstellungen.yaml", bestellung={
        "liefertag": "Mo", "mindestbestellwert_eur": 5, "max_lieferungen_pro_woche": 2,
        "zweite_lieferung_nach_tagen": 3, "bestaetigung_erforderlich": True})
    catalog = load_catalog(data)
    shopping = build_shopping_plan(catalog, generate_week(catalog, 0))
    assert [d.day for d in shopping.deliveries] == [0, 3]
    assert not shopping.spoilage_risks
    second = {l.ingredient_id for l in shopping.deliveries[1].lines}
    assert "banane" in second and "basmatireis" not in second


# --- Hooks -------------------------------------------------------------------

def run_hook(script, event, root=ROOT):
    return subprocess.run([sys.executable, str(root / "scripts" / "hooks" / script)],
                          input=json.dumps(event), capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """Minimale Repo-Kopie, damit Hook-Tests die echten Regeln nicht anfassen."""
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts")
    (tmp_path / "data").mkdir()
    (tmp_path / ".claude").mkdir()
    shutil.copy(DATA_DIR / "regeln.yaml", tmp_path / "data" / "regeln.yaml")
    return tmp_path


@pytest.mark.parametrize("tool", ["Edit", "Write"])
def test_rule_edits_require_confirmation(repo, tool):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool,
             "tool_input": {"file_path": str(repo / "data" / "regeln.yaml")}}
    out = json.loads(run_hook("regeln_schuetzen.py", event, repo).stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_other_edits_pass_without_prompt(repo):
    event = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
             "tool_input": {"file_path": str(repo / "data" / "vorlieben.yaml")}}
    assert run_hook("regeln_schuetzen.py", event, repo).stdout.strip() == ""


def test_harmless_bash_does_not_prompt_or_block(repo):
    event = {"hook_event_name": "PostToolUse", "tool_name": "Bash",
             "tool_input": {"command": 'git commit -m "Grundregeln in data/regeln.yaml"'}}
    result = run_hook("regeln_schuetzen.py", event, repo)
    assert result.returncode == 0 and result.stdout.strip() == ""


def test_bash_change_to_rules_is_reverted(repo):
    rules = repo / "data" / "regeln.yaml"
    original = rules.read_text(encoding="utf-8")
    event = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "true"}}
    run_hook("regeln_schuetzen.py", event, repo)          # Freigabe-Stand anlegen
    rules.write_text(original.replace("min: 3100", "min: 2000"), encoding="utf-8")
    result = run_hook("regeln_schuetzen.py", event, repo)
    assert result.returncode == 2
    assert rules.read_text(encoding="utf-8") == original


def test_approved_edit_becomes_new_baseline(repo):
    rules = repo / "data" / "regeln.yaml"
    bash = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "true"}}
    run_hook("regeln_schuetzen.py", bash, repo)
    changed = rules.read_text(encoding="utf-8").replace("min: 3100", "min: 3000")
    rules.write_text(changed, encoding="utf-8")            # Edit nach deiner Erlaubnis
    edit = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": str(rules)}}
    assert run_hook("regeln_schuetzen.py", edit, repo).returncode == 0
    assert run_hook("regeln_schuetzen.py", bash, repo).returncode == 0
    assert rules.read_text(encoding="utf-8") == changed
