# rakkuun

Automatically shop my meals – Ernährungsplan erstellen, Nährwerte prüfen und die
Zutaten automatisch bei [MyTime](https://www.mytime.de) bestellen.

## Stufen

1. **Ernährungsplan als Daten** – Profil & Ziele (`data/profile.yaml`), Zutaten mit
   Nährwerten, Packungsgrößen, Preisen und Haltbarkeit (`data/ingredients.yaml`),
   Rezepte (`data/recipes.yaml`). ✅ Grundgerüst, echte Werte folgen.
2. **Wochenplan prüfen & Einkaufsliste** – Makros/Mikros pro Tag gegen die Ziele,
   Einkaufsliste auf Packungen gerundet. ✅
   - Aufteilung auf 1 oder 2 Lieferungen pro Woche nach Haltbarkeit
   - Mindestbestellwert (70 €) pro Lieferung; zu kleine Warenkörbe werden mit
     lange haltbaren Vorratsartikeln aufgefüllt
   - Warnung, wenn frische Zutaten vor dem Verbrauch verderben würden
3. **Wochenplan automatisch erzeugen** (Claude) – offen
4. **MyTime-Warenkorb automatisch befüllen**, Bestellung erst nach Bestätigung – offen

## Nutzung

```bash
pip install -r requirements.txt
python -m rakkuun data/plans/beispiel-woche.yaml   # Bericht als Markdown
python -m pytest -q
```
