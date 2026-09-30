# rakkuun

Automatically shop my meals – Ernährungsplan nach festen Grundregeln erzeugen, im Gespräch
an Vorlieben anpassen und die Zutaten automatisch bei [MyTime](https://www.mytime.de) bestellen.

## Wie es funktioniert

```
Grundregeln (regeln.yaml) ──┐
Vorlieben (vorlieben.yaml) ─┤
Wochenvorlage + Rezepte ────┼─▶ Wochenplan ─▶ Regelprüfung ─▶ Einkaufsliste ─▶ Bestätigung ─▶ MyTime
Gewicht + Vorrat ───────────┘                  (❌ = Stopp)    (Vorrat, 70 €,    (du)
                                                               Haltbarkeit)
```

- **Grundregeln** (aus Tages-Ernährungsplan v5/v6): Kalorien je Tagestyp, Protein/Carbs/Fett
  pro kg Körpergewicht, Ballaststoffe, Calcium, Eisen, Magnesium, Zink, max. 2 Paranüsse,
  täglich Leinsamen/rohes Obst/Vitamin-A-Gemüse, Gyros max. 4×/Woche, Zero-Prep, ≤ 20 Min
  Handarbeit, Kalorien-Regel über die Waage und Stellschrauben in fester Reihenfolge.
- **Vorlieben** änderst du im Gespräch mit Claude in diesem Repo. Die Regeln werden dabei
  technisch erzwungen:
  - Nach jeder Änderung an `data/` prüft ein Hook alle Regeln. Bei einem Verstoß muss der
    Agent eine andere Lösung finden oder dir den Konflikt erklären.
  - Änderungen an `data/regeln.yaml` gehen nur mit deiner ausdrücklichen Bestätigung.
  - GitHub Actions prüft jeden Push noch einmal.
- **Wochenplan**: Jede Woche wird er aus der Vorlage erzeugt. Die Hülsenfrucht wechselt
  wöchentlich, Gyros kommt bevorzugt an Spieltage, Rote-Bete-Saft an Spieltage, und leichte
  Tage bekommen kleinere Portionen.
- **Einkauf**: Der Vorrat wird abgezogen, alles auf Packungen gerundet und nach Haltbarkeit
  auf 1–2 Lieferungen verteilt. Liegt ein Warenkorb unter 70 €, wird mit lange haltbaren
  Artikeln aus dem Plan aufgefüllt, und der Rest wird als Vorrat verbucht.

## Stand

1. Grundregeln, Rezepte, Zutaten aus deinem Plan ✅
2. Wochenplan, Regelprüfung, Einkaufsliste ✅
3. Gespräch mit dem Agenten + Schutz der Grundregeln ✅ (`CLAUDE.md`, `.claude/settings.json`)
4. MyTime-Anbindung (Artikel zuordnen, Warenkorb füllen, Bestätigung) – offen
5. Wöchentliche Automatik – offen

## Nutzung

```bash
pip install -r requirements.txt
python -m rakkuun woche             # Plan + Prüfung + Bestellvorschlag für nächste Woche
python -m rakkuun pruefen --alle    # Grundregeln für alle Rotationswochen prüfen
python -m rakkuun gewicht 65.4      # Gewicht eintragen
python -m pytest -q
```
