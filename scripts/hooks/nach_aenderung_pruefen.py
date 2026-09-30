"""PostToolUse-Hook: Nach jeder Änderung an data/ werden alle Grundregeln geprüft.

Verstößt der Plan danach gegen eine Regel, bekommt der Agent die Fehler zurück
und muss eine Lösung finden, die deine Vorlieben UND die Regeln erfüllt."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

event = json.load(sys.stdin)
inp = event.get("tool_input", {})
target = inp.get("file_path", "") or inp.get("command", "")
if "data/" not in target.replace("\\", "/") and "rakkuun" not in target:
    sys.exit(0)

result = subprocess.run([sys.executable, "-m", "rakkuun", "pruefen"], cwd=ROOT,
                        capture_output=True, text=True)
if result.returncode != 0:
    print("GRUNDREGELN VERLETZT – so darf der Plan nicht bleiben. Finde eine Anpassung, die die "
          "Vorliebe erfüllt und alle Regeln einhält, oder erkläre dem Nutzer den Konflikt.\n\n"
          + result.stdout + result.stderr, file=sys.stderr)
    sys.exit(2)
