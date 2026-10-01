"""Schutz der Grundregeln (data/regeln.yaml).

PreToolUse  (Edit/Write): Bevor der Agent die Datei bearbeitet, wirst du um Erlaubnis gefragt.
PostToolUse (Edit/Write): Nach deiner Erlaubnis wird der neue Stand als freigegeben gespeichert.
PostToolUse (Bash):       Hat ein Shell-Befehl die Datei am Freigabeprozess vorbei verändert,
                          wird sie zurückgesetzt und der Agent muss den Weg mit Bestätigung gehen.

Es wird also nur gefragt, wenn die Regeln wirklich geändert werden sollen – nicht bei
harmlosen Befehlen, die die Datei nur erwähnen oder lesen."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "data" / "regeln.yaml"
APPROVED = ROOT / ".claude" / "regeln.freigegeben"   # lokaler Stand, nicht im Git

event = json.load(sys.stdin)
tool = event.get("tool_name", "")
phase = event.get("hook_event_name", "PreToolUse")
path = event.get("tool_input", {}).get("file_path", "").replace("\\", "/")
targets_rules = path.endswith("data/regeln.yaml")

if not APPROVED.exists() and RULES.exists():
    APPROVED.write_bytes(RULES.read_bytes())

if phase == "PreToolUse":
    if tool in ("Edit", "Write", "MultiEdit") and targets_rules:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Änderung an deinen GRUNDREGELN (data/regeln.yaml) – bitte nur "
                                        "bestätigen, wenn du diese Regel wirklich ändern willst.",
        }}))
    sys.exit(0)

# PostToolUse
if tool in ("Edit", "Write", "MultiEdit") and targets_rules:
    APPROVED.write_bytes(RULES.read_bytes())       # du hast zugestimmt
elif tool == "Bash" and RULES.exists() and RULES.read_bytes() != APPROVED.read_bytes():
    RULES.write_bytes(APPROVED.read_bytes())
    print("data/regeln.yaml wurde per Shell-Befehl verändert und ist zurückgesetzt. Grundregeln "
          "nur mit dem Edit-Tool ändern – dann wird der Nutzer um Erlaubnis gefragt.", file=sys.stderr)
    sys.exit(2)
