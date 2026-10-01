"""Erzeugt die Übersichtsseite „Mein Ernährungsplan“ (HTML) aus den aktuellen Daten.

Die Seite ist reine Ansicht: Tagesplan, Nährwerte gegen die Grundregeln,
Einkaufsliste, Gewichtsverlauf. Geändert wird im Gespräch mit dem Agenten."""

from __future__ import annotations

from datetime import date
from html import escape

from .data import Catalog
from .nutrition import nutrients
from .plan import Day, Week, day_grams, meal_grams
from .rules import LABELS, Finding, current_weight
from .shopping import ShoppingPlan, weekly_cost

MEAL_LABELS = {"fruehstueck": "Frühstück", "mittag": "Mittag", "abend": "Abend", "snack": "Abendsnack",
               "extra": "Extra"}
MEAL_ORDER = ["fruehstueck", "mittag", "abend", "snack", "extra"]
NUTRIENTS = ["kcal", "protein", "carbs", "fat", "fiber", "calcium_mg", "iron_mg", "magnesium_mg", "zinc_mg"]

CSS = """
/* Layout: eine ruhige Spalte wie eine Küchen-Karteikarte; Mahlzeiten als Karten, Zahlen in Mono. */
:root {
  --bg: #f2f4f1; --surface: #ffffff; --fg: #1b2420; --muted: #5a6962; --line: #d8dfda;
  --accent: #1f5f7a; --accent-soft: #e3eef3;
  --good: #2e7d4f; --warn: #a86a12; --bad: #b3412e; --band: #dcebe1;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "Atkinson Hyperlegible", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #111715; --surface: #19211e; --fg: #e5ebe7; --muted: #9aaaa2; --line: #2c3833;
  --accent: #74b6d1; --accent-soft: #1d2f37;
  --good: #5dbb85; --warn: #e0a84a; --bad: #e88672; --band: #20372a; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #111715; --surface: #19211e; --fg: #e5ebe7; --muted: #9aaaa2; --line: #2c3833;
  --accent: #74b6d1; --accent-soft: #1d2f37;
  --good: #5dbb85; --warn: #e0a84a; --bad: #e88672; --band: #20372a; color-scheme: dark }

* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font: 16px/1.55 var(--body); }
.wrap { max-width: 760px; margin: 0 auto; padding-inline: 16px; padding-block: 28px 56px;
        display: grid; gap: 40px; }
h1, h2, h3 { font-family: var(--display); text-wrap: balance; margin: 0; line-height: 1.15; }
h1 { font-size: clamp(30px, 7vw, 44px); font-weight: 700; letter-spacing: -0.02em; }
h2 { font-size: 22px; font-weight: 650; }
h3 { font-size: 17px; font-weight: 650; }
p { margin: 0; }
.eyebrow { font: 600 12px/1.2 var(--mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); }
section { display: grid; gap: 16px; }
.section-head { display: grid; gap: 4px; }

header { display: grid; gap: 14px; }
.facts { display: flex; flex-wrap: wrap; gap: 8px 20px; color: var(--muted); font-size: 15px; }
.facts b { color: var(--fg); font-weight: 600; }
.status { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px;
          font-weight: 600; font-size: 14px; width: fit-content; border: 1px solid currentColor; }
.status.ok { color: var(--good); } .status.err { color: var(--bad); }

.meals { display: grid; gap: 12px; }
.meal { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px;
        display: grid; gap: 10px; min-width: 0; }
.meal-top { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 4px 12px; }
.meal-macros { font-size: 13px; color: var(--muted); }
.ing { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.ing li { display: grid; grid-template-columns: 4.5em 1fr; gap: 10px; }
.ing .g { text-align: right; color: var(--muted); }
.how { font-size: 14px; color: var(--muted); border-top: 1px dashed var(--line); padding-top: 10px; }
.chip { font: 600 12px/1 var(--mono); padding: 4px 8px; border-radius: 6px; background: var(--accent-soft);
        color: var(--accent); white-space: nowrap; }

.nut { display: grid; gap: 14px; background: var(--surface); border: 1px solid var(--line);
       border-radius: 10px; padding: 18px; }
.nut-row { display: grid; grid-template-columns: minmax(7.5em, 9em) 1fr; gap: 6px 14px; align-items: center; }
.nut-label { display: grid; }
.nut-label span:last-child { font-size: 12px; color: var(--muted); }
.track { position: relative; height: 22px; }
.track .base { position: absolute; left: 0; right: 0; top: 10px; height: 2px; background: var(--line); }
.track .band { position: absolute; top: 4px; height: 14px; background: var(--band); border-radius: 3px; }
.track .val { position: absolute; top: 3px; width: 4px; height: 16px; border-radius: 2px; margin-left: -2px; }
.nut-value { grid-column: 2; display: flex; justify-content: space-between; gap: 8px; font-size: 13px; }
.ok-t { color: var(--good); } .warn-t { color: var(--warn); } .bad-t { color: var(--bad); }
.val.ok { background: var(--good); } .val.warn { background: var(--warn); } .val.bad { background: var(--bad); }
.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); }
.legend i { display: inline-block; width: 18px; height: 10px; border-radius: 2px; background: var(--band);
            vertical-align: -1px; margin-right: 6px; }

.findings { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
.table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 15px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font: 600 12px/1.2 var(--mono); letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
td.r, th.r { text-align: right; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
.rule { display: block; font-size: 13px; color: var(--muted); }
tfoot td { font-weight: 700; border-top: 2px solid var(--line); }
.note { font-size: 14px; color: var(--muted); }
.product { display: block; font-weight: 700; }
.flag { display: block; margin-top: 6px; font-size: 13px; padding: 6px 8px; border-radius: 6px;
        border-left: 3px solid currentColor; }
.flag.pruefen { color: var(--warn); } .flag.fehlt { color: var(--bad); }

.habits { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
.weight svg { width: 100%; height: auto; display: block; }
.empty { background: var(--surface); border: 1px dashed var(--line); border-radius: 10px; padding: 18px;
         color: var(--muted); }
footer { font-size: 14px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 16px; }
@media (max-width: 480px) { .nut-row { grid-template-columns: 1fr; } .nut-value { grid-column: 1; } }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700'
         '&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Mono:wght@400;600&display=swap">')


def _fmt(value: float, unit: str) -> str:
    return f"{value:,.0f}".replace(",", ".") + (f" {unit}" if unit else "")


def _targets(catalog: Catalog, day: Day) -> dict[str, tuple[float | None, float | None]]:
    """Grenzen je Nährstoff für diesen Tagestyp (nur Regeln der Stufe 'fehler' bilden das Zielband)."""
    weight = current_weight(catalog)
    bounds: dict[str, list[float | None]] = {}
    for rule in catalog.rules.get("naehrwerte", []):
        if rule.get("tagestyp") not in (None, day.typ) or rule.get("stufe") != "fehler":
            continue
        lo = rule.get("min", rule["min_pro_kg"] * weight if "min_pro_kg" in rule else None)
        hi = rule.get("max", rule["max_pro_kg"] * weight if "max_pro_kg" in rule else None)
        cur = bounds.setdefault(rule["naehrstoff"], [None, None])
        cur[0] = lo if lo is not None else cur[0]
        cur[1] = hi if hi is not None else cur[1]
    return {k: (v[0], v[1]) for k, v in bounds.items()}


def _meals_html(catalog: Catalog, day: Day) -> str:
    grouped: dict[str, list[str]] = {}
    for recipe_id in day.meals:
        grouped.setdefault(catalog.recipes[recipe_id].mahlzeit, []).append(recipe_id)
    cards = []
    for slot in [s for s in MEAL_ORDER if s in grouped]:
        recipes = [catalog.recipes[r] for r in grouped[slot]]
        grams: dict[str, float] = {}
        for r in grouped[slot]:
            for ingredient_id, amount in meal_grams(catalog, r, day).items():
                grams[ingredient_id] = grams.get(ingredient_id, 0) + amount
        values = nutrients(catalog, grams)
        minutes = sum(r.active_minutes for r in recipes)
        items = "".join(
            f'<li><span class="g num">{amount:.0f} g</span><span>{escape(catalog.ingredients[i].name)}</span></li>'
            for i, amount in grams.items())
        how = " ".join(escape(r.anleitung) for r in recipes if r.anleitung)
        title = " + ".join(escape(r.name) for r in recipes)
        cards.append(f"""
      <article class="meal">
        <div class="meal-top">
          <span class="eyebrow">{MEAL_LABELS.get(slot, slot)}</span>
          <span class="chip">{minutes} Min Handarbeit</span>
        </div>
        <h3>{title}</h3>
        <p class="meal-macros num">{values.get('kcal', 0):.0f} kcal · {values.get('protein', 0):.0f} g Protein ·
          {values.get('carbs', 0):.0f} g KH · {values.get('fat', 0):.0f} g Fett</p>
        <ul class="ing">{items}</ul>
        {f'<p class="how">{how}</p>' if how else ''}
      </article>""")
    return "".join(cards)


def _nutrients_html(catalog: Catalog, day: Day) -> str:
    values = nutrients(catalog, day_grams(catalog, day))
    targets = _targets(catalog, day)
    rows = []
    for key in NUTRIENTS:
        label, unit = LABELS[key]
        value = values.get(key, 0.0)
        lo, hi = targets.get(key, (None, None))
        scale = max(value, hi or 0, lo or 0) * 1.15 or 1
        band_lo = (lo or 0) / scale * 100
        band_hi = (hi / scale * 100) if hi else 100
        if lo is not None and value < lo:
            state, text = "bad", "↓ unter Ziel"
        elif hi is not None and value > hi:
            state, text = "bad", "↑ über Ziel"
        else:
            state, text = "ok", "✓ im Ziel"
        if lo is not None and hi is not None:
            goal = f"Ziel {_fmt(lo, '')}–{_fmt(hi, unit)}"
        elif lo is not None:
            goal = f"Ziel ≥ {_fmt(lo, unit)}"
        elif hi is not None:
            goal = f"Ziel ≤ {_fmt(hi, unit)}"
        else:
            goal = "kein Zielwert"
        tooltip = f"{label}: {_fmt(value, unit)} · {goal}"
        rows.append(f"""
        <div class="nut-row" title="{escape(tooltip)}">
          <div class="nut-label"><span>{label}</span><span class="num">{goal}</span></div>
          <div class="track" role="img" aria-label="{escape(tooltip)}">
            <div class="base"></div>
            <div class="band" style="left:{band_lo:.1f}%;width:{band_hi - band_lo:.1f}%"></div>
            <div class="val {state}" style="left:{min(value / scale * 100, 100):.1f}%"></div>
          </div>
          <div class="nut-value"><span class="num">{_fmt(value, unit)}</span><span class="{state}-t">{text}</span></div>
        </div>""")
    return "".join(rows)


def _findings_html(findings: list[Finding]) -> str:
    if not findings:
        return ""
    seen, items = set(), []
    for f in sorted(findings, key=lambda f: not f.is_error):
        key = (f.stufe, f.text)
        if key in seen:
            continue
        seen.add(key)
        cls = "bad-t" if f.is_error else "warn-t"
        icon = "✕ Verstoß" if f.is_error else "Hinweis"
        items.append(f'<li><span class="{cls}">{icon}:</span> {escape(f.text)}'
                     + (f' <span class="muted">– {escape(f.grund)}</span>' if f.grund else "") + "</li>")
    return f'<ul class="findings">{"".join(items)}</ul>'


def _shopping_html(catalog: Catalog, week: Week, shopping: ShoppingPlan) -> str:
    parts = []
    for delivery in shopping.deliveries:
        rows = []
        for line in delivery.lines:
            product = (f'<span class="product">{escape(line.product)}</span>' if line.product
                       else '<span class="product bad-t">Kein MyTime-Produkt zugeordnet</span>')
            flag = ""
            if line.status in ("pruefen", "fehlt"):
                label = "Bitte entscheiden" if line.status == "pruefen" else "Fehlt bei MyTime"
                flag = f'<span class="flag {line.status}">{label}: {escape(line.hinweis)}</span>'
            price = f"{line.total_eur:.2f} €" if line.product else "–"
            rows.append(f'<tr><td>{product}<span class="rule">{escape(line.name)} · '
                        f'<span class="num">{line.grams_needed:.0f} g pro Woche</span></span>{flag}</td>'
                        f'<td class="r num">{line.packages}×</td><td class="r num">{price}</td></tr>')
        for line in delivery.filler:
            rows.append(f'<tr><td>{escape(line.product or line.name)} <span class="muted">(Vorrat)</span></td>'
                        f'<td class="r num">{line.packages}×</td><td class="r num">{line.total_eur:.2f} €</td></tr>')
        minimum = catalog.ordering["mindestbestellwert_eur"]
        parts.append(f"""
      <div class="table-wrap">
        <table>
          <thead><tr><th>Artikel</th><th class="r">Pack.</th><th class="r">Preis</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
          <tfoot><tr><td colspan="2">Summe (Mindestbestellwert {minimum:.0f} €)</td>
            <td class="r num">{delivery.total_eur:.2f} €</td></tr></tfoot>
        </table>
      </div>""")
    notes = [escape(n) for n in shopping.notes]
    if shopping.spoilage_risks:
        first: dict[str, str] = {}
        for ingredient_id, d in sorted(shopping.spoilage_risks, key=lambda r: r[1]):
            first.setdefault(ingredient_id, week.days[d].weekday)
        notes += [f"{escape(catalog.ingredients[i].name)} ist ab {wd} evtl. sehr reif – z. B. eingefroren ins Oatmeal."
                  for i, wd in first.items()]
    open_items = [l for d in shopping.deliveries for l in d.lines if l.status != "ok"]
    notes.append("Preise und Produkte von mytime.de (abgefragt ohne Login, Lieferregion kann abweichen)."
                 + (f" {len(open_items)} Artikel brauchen noch deine Entscheidung." if open_items else ""))
    if catalog.ordering.get("bestaetigung_erforderlich", True):
        notes.append("Bestellt wird erst nach deiner Bestätigung.")
    return "".join(parts) + "".join(f'<p class="note">{n}</p>' for n in notes)


def _weight_html(catalog: Catalog) -> str:
    points = sorted(catalog.weights.items())
    if len(points) < 2:
        current = f"Aktuell hinterlegt: {current_weight(catalog):.1f} kg. " if points or catalog.rules else ""
        return (f'<div class="empty">{current}Noch zu wenige Messungen für einen Verlauf. Wieg dich 1× pro Woche '
                'morgens nüchtern und sag dem Agenten z. B. „Gewicht 65,4“.</div>')
    w, h, pad_l, pad_r, pad_t, pad_b = 640, 180, 44, 16, 16, 28
    days = [date.fromisoformat(d).toordinal() for d, _ in points]
    kgs = [kg for _, kg in points]
    lo, hi = min(kgs) - 0.5, max(kgs) + 0.5
    x = lambda d: pad_l + (d - days[0]) / max(days[-1] - days[0], 1) * (w - pad_l - pad_r)
    y = lambda kg: pad_t + (hi - kg) / (hi - lo) * (h - pad_t - pad_b)
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(d):.1f},{y(kg):.1f}" for i, (d, kg) in enumerate(zip(days, kgs)))
    area = path + f" L{x(days[-1]):.1f},{h - pad_b} L{x(days[0]):.1f},{h - pad_b} Z"
    dots = "".join(f'<circle cx="{x(d):.1f}" cy="{y(kg):.1f}" r="5" fill="var(--accent)" stroke="var(--surface)" '
                   f'stroke-width="2"><title>{ds}: {kg:.1f} kg</title></circle>'
                   for d, kg, (ds, _) in zip(days, kgs, points))
    ticks = "".join(f'<text x="{pad_l - 8}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="12" fill="var(--muted)" '
                    f'font-family="var(--mono)">{v:.0f}</text><line x1="{pad_l}" x2="{w - pad_r}" y1="{y(v):.1f}" '
                    f'y2="{y(v):.1f}" stroke="var(--line)"/>'
                    for v in range(int(lo + 0.999), int(hi) + 1))
    first, last = points[0], points[-1]
    return f"""
      <div class="nut weight">
        <svg viewBox="0 0 {w} {h}" role="img" aria-label="Gewichtsverlauf von {first[1]:.1f} auf {last[1]:.1f} kg">
          {ticks}
          <path d="{area}" fill="var(--accent-soft)"/>
          <path d="{path}" fill="none" stroke="var(--accent)" stroke-width="2"/>
          {dots}
          <text x="{pad_l}" y="{h - 6}" font-size="12" fill="var(--muted)" font-family="var(--mono)">{first[0]}</text>
          <text x="{w - pad_r}" y="{h - 6}" text-anchor="end" font-size="12" fill="var(--muted)" font-family="var(--mono)">{last[0]}</text>
        </svg>
      </div>"""


def render_site(catalog: Catalog, week: Week, findings: list[Finding], shopping: ShoppingPlan | None) -> str:
    day = week.days[0]
    errors = [f for f in findings if f.is_error]
    status = ('<span class="status ok">✓ Alle Grundregeln eingehalten</span>' if not errors else
              f'<span class="status err">✕ {len(errors)} Regelverstöße – nicht bestellbar</span>')
    same = catalog.preferences.get("jeden_tag_gleich")
    legume = catalog.ingredients[week.legume].name.split(",")[0] if week.legume else "–"
    total_minutes = sum(catalog.recipes[r].active_minutes for r in day.meals)
    habits = "".join(f"<li>{escape(h)}</li>" for h in catalog.rules.get("gewohnheiten") or [])
    shopping_html = (_shopping_html(catalog, week, shopping) if shopping else
                     '<div class="empty">Kein Bestellvorschlag, solange der Plan gegen Grundregeln verstößt.</div>')
    return f"""<title>Mein Ernährungsplan</title>
{FONTS}
<style>{CSS}</style>
<main class="wrap">
  <header>
    <span class="eyebrow">KW {week.iso_week} · Liefertag {catalog.ordering['liefertag']}</span>
    <h1>{'Dein Tag, jeden Tag dieser Woche' if same else 'Dein Wochenplan'}</h1>
    <div class="facts">
      <span>Gewicht <b class="num">{current_weight(catalog):.1f} kg</b></span>
      <span>Ziel <b class="num">{'–'.join(str(v) for v in catalog.rules.get('zielgewicht_kg', []))} kg</b></span>
      <span>Hülsenfrucht der Woche <b>{escape(legume)}</b></span>
      <span>Handarbeit <b class="num">{total_minutes} Min/Tag</b></span>
      <span>Verbrauch <b class="num">≈ {weekly_cost(catalog, week):.0f} €/Woche</b></span>
    </div>
    {status}
  </header>

  <section>
    <div class="section-head"><span class="eyebrow">Der Tag</span><h2>Was du isst</h2></div>
    <div class="meals">{_meals_html(catalog, day)}</div>
  </section>

  <section>
    <div class="section-head"><span class="eyebrow">Pro Tag</span><h2>Nährwerte gegen deine Grundregeln</h2></div>
    <div class="nut">
      <div class="legend"><span><i></i>Zielbereich aus deinen Grundregeln</span><span class="ok-t">✓ im Ziel</span>
        <span class="bad-t">↑↓ außerhalb</span></div>
      {_nutrients_html(catalog, day)}
    </div>
    {_findings_html(findings)}
  </section>

  <section>
    <div class="section-head"><span class="eyebrow">MyTime</span><h2>Einkaufsliste für 7 Tage</h2></div>
    {shopping_html}
  </section>

  <section>
    <div class="section-head"><span class="eyebrow">Kalorien-Regel</span><h2>Gewichtsverlauf</h2></div>
    {_weight_html(catalog)}
  </section>

  <section>
    <div class="section-head"><span class="eyebrow">Gewohnheiten</span><h2>Nicht vergessen</h2></div>
    <ul class="habits">{habits}</ul>
  </section>

  <footer>Stand {date.today().strftime('%d.%m.%Y')}. Ändern willst du etwas? Sag es deinem Ernährungs-Agenten
    in Claude – diese Seite zeigt dann den neuen Plan.</footer>
</main>
"""
