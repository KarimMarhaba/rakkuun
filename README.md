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
- **Vorlieben** werden im Gespräch mit dem Ernährungs-Agenten geändert. Die Regeln werden dabei
  technisch erzwungen:
  - Nach jeder Änderung an `data/` prüft ein Hook alle Regeln. Bei einem Verstoß muss der
    Agent eine andere Lösung finden oder dir den Konflikt erklären.
  - Änderungen an `data/regeln.yaml` gehen nur mit deiner ausdrücklichen Bestätigung.
  - GitHub Actions prüft jeden Push noch einmal.
- **Wochenplan**: Ein Tagesplan, der jeden Wochentag gleich läuft. Abwechslung gibt es nur
  von Woche zu Woche (z. B. wechselt die Hülsenfrucht). Spieltage und leichte Tage sind
  vorbereitet, aber aktuell aus.
- **Einkauf**: Bestellt wird, wenn der Vorrat ausgeht – die Lieferung kommt am Tag, bevor die erste Zutat leer ist, und deckt 7 Tage. Der Vorrat wird abgezogen und alles auf Packungen
  gerundet. Alles wird für 7 Tage bestellt; was bis zum Wochenende sehr reif
  wird (Bananen), ist markiert. Liegt der Warenkorb unter 70 €, wird mit lange haltbaren
  Artikeln aus dem Plan aufgefüllt, und der Rest wird als Vorrat verbucht.
- **Plan-Review**: „Lass uns den Ernährungsplan überarbeiten“ sagen. Der Ablauf steht in der
  Agenten-Anleitung, die Original-Pläne liegen in `docs/plaene/`.

## Übersichtsseite

Plan, Nährwerte, Einkaufsliste und Gewicht als private Übersichtsseite (erzeugt mit `python -m rakkuun seite`).

## Stand

1. Grundregeln, Rezepte, Zutaten aus deinem Plan ✅
2. Wochenplan, Regelprüfung, Einkaufsliste ✅
3. Gespräch mit dem Agenten + Schutz der Grundregeln ✅
4. MyTime: Artikel mit echten Preisen ✅ · Warenkorb automatisch befüllen ✅ · Bestellen bleibt manuell
5. Wöchentliche Automatik – offen

## Nutzung

```bash
pip install -r requirements.txt
python -m rakkuun woche             # Plan + Prüfung + Bestellvorschlag für nächste Woche
python -m rakkuun pruefen --alle    # Grundregeln für alle Rotationswochen prüfen
python -m rakkuun gewicht 65.4      # Gewicht eintragen
python -m rakkuun seite             # Übersichtsseite nach build/plan.html
python -m rakkuun warenkorb         # MyTime-Warenkorb befüllen (bestellt nie; --nur-ansehen)
python -m rakkuun vorrat            # Bestand, Reichweite, nächster Liefertermin
python -m pytest -q
```
