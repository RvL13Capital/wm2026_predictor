#!/usr/bin/env python3
"""Validate a live_state.json before feeding it to the simulators (S18).

    python3 scripts/validate_live_state.py data/live_state.json

Exit codes: 0 valid (warnings allowed), 1 errors found, 2 unreadable file.
Run this after EVERY edit during the tournament — a typo'd key is a silent
no-op inside the simulators (docs/LIVE_STATE.md).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.live_state import validate_live_state


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        print(f"❌ cannot read {path}: {e}")
        sys.exit(2)

    errors, warnings = validate_live_state(state)
    for w in warnings:
        print(f"⚠  {w}")
    for e in errors:
        print(f"❌ {e}")
    if errors:
        print(f"\n{len(errors)} error(s) — fix before using this file.")
        sys.exit(1)
    print(f"✅ {path}: {len(state)} override(s) valid"
          + (f" ({len(warnings)} warning(s))" if warnings else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
