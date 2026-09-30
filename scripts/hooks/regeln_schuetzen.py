"""PreToolUse-Hook: Änderungen an den Grundregeln brauchen immer deine Zustimmung.

Egal wie das Gespräch läuft – bevor der Agent data/regeln.yaml anfasst,
fragt Claude Code dich ausdrücklich um Erlaubnis."""

import json
import re
import sys

PROTECTED = "data/regeln.yaml"
# Shell-Befehle, die eine Datei verändern können
WRITING = re.compile(r"(>|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b|\bpython|\bperl\b|\bgit\s+(checkout|restore|apply))")

event = json.load(sys.stdin)
tool = event.get("tool_name", "")
inp = event.get("tool_input", {})

touches = False
if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    touches = inp.get("file_path", "").replace("\\", "/").endswith(PROTECTED)
elif tool == "Bash":
    cmd = inp.get("command", "")
    touches = "regeln.yaml" in cmd and bool(WRITING.search(cmd))

if touches:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": "Änderung an deinen GRUNDREGELN (data/regeln.yaml) – bitte nur bestätigen, "
                                    "wenn du diese Regel wirklich ändern willst.",
    }}))
