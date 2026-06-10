"""live_state.json validation (plan step S18).

A live-state file forces real results into the simulators
(vectorized_mc --live-state, edge_scanner --live-state). A typo'd team name
or match id previously failed SILENTLY (the override just never matched and
the match kept being simulated) — the worst failure mode mid-tournament.

Schema — a single JSON object; two key forms, values always [goals_a, goals_b]:
  "Mexico vs South Africa": [2, 0]   # pairing-keyed (orientation auto-swapped)
  "M73": [2, 1]                      # match-id-keyed (M73..M104), applied in
                                     # bracket orientation to that slot
"""
import re
from typing import Dict, List, Tuple

import predictor
import tournament_bonusfragen as tb

_MATCH_ID_RE = re.compile(r"^M(\d{1,3})$")
_VALID_MATCH_IDS = {f"M{n}" for n in range(73, 105)}   # R32..Final (incl. M103 3rd place)
MAX_GOALS = 15                                          # grid bound per side


def _known_team(name: str) -> bool:
    canon = predictor.TEAM_NAME_MAPPING.get(name.strip().lower(), name.strip())
    return canon in predictor.WORLD_CUP_2026_TEAMS


def validate_live_state(state: dict) -> Tuple[List[str], List[str]]:
    """Returns (errors, warnings). Errors make the file unusable; warnings
    flag entries that will be silently ignored by the simulators."""
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(state, dict):
        return [f"live_state must be a JSON object, got {type(state).__name__}"], []

    for key, val in state.items():
        # --- value shape ---
        if (not isinstance(val, (list, tuple)) or len(val) != 2
                or not all(isinstance(g, int) and not isinstance(g, bool) for g in val)):
            errors.append(f"{key!r}: value must be [goals_a, goals_b] integers, got {val!r}")
            continue
        ga, gb = val
        if not (0 <= ga <= MAX_GOALS and 0 <= gb <= MAX_GOALS):
            errors.append(f"{key!r}: goals out of range 0..{MAX_GOALS}: {val!r}")
            continue

        # --- key form ---
        m = _MATCH_ID_RE.match(key.strip())
        if m:
            if key.strip() not in _VALID_MATCH_IDS:
                errors.append(f"{key!r}: match id outside the KO bracket M73..M104")
            elif ga == gb:
                errors.append(f"{key!r}: KO override cannot be a draw ({ga}:{gb}) — "
                              f"the bracket needs a winner")
            continue
        if " vs " in key:
            a, b = key.split(" vs ", 1)
            unknown = [n for n in (a, b) if not _known_team(n)]
            if unknown:
                errors.append(f"{key!r}: unknown team name(s) {unknown} — the override "
                              f"would NEVER match (silent no-op). Use canonical names "
                              f"or spellings from predictor.TEAM_NAME_MAPPING.")
            else:
                ca = predictor.TEAM_NAME_MAPPING.get(a.strip().lower(), a.strip())
                cb = predictor.TEAM_NAME_MAPPING.get(b.strip().lower(), b.strip())
                if (ca, cb) != (a.strip(), b.strip()):
                    warnings.append(f"{key!r}: non-canonical spelling — simulators match "
                                    f"EXACT canonical names; rewrite as '{ca} vs {cb}'.")
            continue
        errors.append(f"{key!r}: key must be 'Team A vs Team B' or a match id 'M73'..'M104'")

    return errors, warnings


def teams_in_groups() -> set:
    out = set()
    for teams in tb.GROUPS.values():
        out.update(teams)
    return out
