"""Recommendation change detection + WhatsApp alerting (ops loop).

Keeps the last published recommendation per scope in a local state file and
diffs every new run against it, so the operator gets ONE alert listing exactly
which recommendations flipped (e.g. after a fresh odds snapshot or an injury
update changes a tip). Wired into the four recommendation-producing CLIs:

    matchday_tips.py            scope "MD<n>"            key "TeamA vs TeamB" -> "a:b"
    ko_tips.py                  scope "KO-<round>"       key "TeamA vs TeamB" -> "a:b"
    tournament_bonusfragen.py   scope "bonusfragen:scalar"     answer keys
    vectorized_mc.py            scope "bonusfragen:vectorized" answer keys

Semantics:
  - First run of a scope records a baseline silently (nothing to compare).
  - New keys (a new matchday/round) are added silently; only VALUE CHANGES on
    existing keys alert.
  - Scopes are merge-updated, never replaced — a partial KO re-run keeps the
    baseline of the matches it didn't touch.
  - The two tournament engines get separate scopes: their answers may
    legitimately differ (S11 divergence) and must not ping-pong alerts.
  - State lives in data/recommendation_state.json (gitignored, per-machine —
    alerts fire on the ops machine, where runs recur), override via
    WM2026_REC_STATE. Load/save never raise: a corrupt/missing state file
    degrades to "record a fresh baseline" (one stderr warning), because an
    alerting bug must never kill a tip run.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATE_PATH = os.path.join(_ROOT, "data", "recommendation_state.json")
STATE_PATH_ENV = "WM2026_REC_STATE"


def _state_path(path: str = None) -> str:
    return path or os.environ.get(STATE_PATH_ENV) or DEFAULT_STATE_PATH


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:                       # corrupt file -> fresh baseline
        sys.stderr.write(f"[rec-state] unreadable {path} ({e}) — re-baselining\n")
        return {}


def diff_and_update(scope: str, recommendations: dict, state_path: str = None) -> list:
    """Diff `recommendations` ({key: value_str}) against the stored scope,
    persist the merged update, and return [(key, old, new), ...] for every
    existing key whose value changed. Never raises."""
    path = _state_path(state_path)
    state = _load(path)
    previous = state.get(scope) or {}
    changes = [(k, previous[k], str(v)) for k, v in recommendations.items()
               if k in previous and previous[k] != str(v)]
    previous.update({k: str(v) for k, v in recommendations.items()})
    state[scope] = previous
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1, ensure_ascii=False, sort_keys=True)
    except Exception as e:
        sys.stderr.write(f"[rec-state] could not persist {path}: {e}\n")
    return changes


def bonusfragen_recommendations(results: dict) -> dict:
    """Flatten a tournament engine results dict (both engines share the
    schema) into comparable answer strings. Semifinalists are sorted — the
    SET is the recommendation, not the order."""
    recs = {}
    if "champion" in results:
        recs["Weltmeister"] = results["champion"]["tip"]
    if "semifinalists" in results:
        recs["Halbfinale"] = ", ".join(sorted(results["semifinalists"]["tips"]))
    if "top_scorer_team" in results:
        recs["Torschützen-Team"] = results["top_scorer_team"]["tip"]
    for group, g in (results.get("group_winners") or {}).items():
        recs[f"Gruppensieger {group}"] = g["tip"]
    return recs


def format_changes_message(scope_label: str, changes: list, max_items: int = 8) -> str:
    """One compact WhatsApp/stdout message: 'key: old → new' per change."""
    if not changes:
        return ""
    lines = [f"WM2026 ⚠ {len(changes)} recommendation(s) changed ({scope_label}):"]
    for key, old, new in changes[:max_items]:
        lines.append(f"• {key}: {old} → {new}")
    if len(changes) > max_items:
        lines.append(f"… +{len(changes) - max_items} more")
    return "\n".join(lines)


def alert_on_changes(scope: str, recommendations: dict, state_path: str = None) -> list:
    """diff_and_update + print + WhatsApp push in one call (the CLI hook).
    Returns the changes. Never raises."""
    from utils import notify
    changes = diff_and_update(scope, recommendations, state_path)
    if changes:
        msg = format_changes_message(scope, changes)
        print(msg, file=sys.stderr)
        if notify.send_whatsapp(msg):
            print("[rec-state] WhatsApp alert sent", file=sys.stderr)
    return changes
