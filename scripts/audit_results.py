#!/usr/bin/env python3
"""Audit live_state.json results against the real schedule (S20 ops integrity check).

Beyond validate_live_state.py (format + canonical names), this cross-checks every result against
data/fifa_2026_schedule.json: does the pairing exist as a real group fixture, in which match/
matchday, and is the orientation as scheduled? Catches results entered for pairings that never
meet (a silent no-op in the sims), cross-group typos, duplicates, and impossible scores.

    python3 scripts/audit_results.py [data/live_state.json]

Exit 0 = every result maps to a real fixture; exit 1 = problems found.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tournament_bonusfragen import GROUPS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_fixtures():
    slot = {f"{g}{i+1}": t for g, ts in GROUPS.items() for i, t in enumerate(ts)}
    # Round-robin matchday from the group's team ORDER (not match-id — those don't map to matchdays:
    # e.g. Group L's round 2 is M49/M50). MD1 {0,1}{2,3} · MD2 {0,2}{1,3} · MD3 {0,3}{1,2}.
    md_of = {frozenset((0, 1)): 1, frozenset((2, 3)): 1, frozenset((0, 2)): 2,
             frozenset((1, 3)): 2, frozenset((0, 3)): 3, frozenset((1, 2)): 3}
    pos = {t: i for ts in GROUPS.values() for i, t in enumerate(ts)}
    sched = json.load(open(os.path.join(ROOT, "data", "fifa_2026_schedule.json")))
    fixtures = {}
    for m in sched:
        if m.get("phase") != "GROUP":
            continue
        a, b, mid = slot[m["team_a_slot"]], slot[m["team_b_slot"]], m["match_id"]
        md = md_of.get(frozenset((pos[a], pos[b])), 0)
        fixtures[frozenset((a, b))] = (mid, m["date"], a, b, md)
    return fixtures


def audit(live_state):
    tg = {t: g for g, ts in GROUPS.items() for t in ts}
    fixtures = build_fixtures()
    seen, lines, problems = set(), [], 0
    for key, score in live_state.items():
        if " vs " not in key:
            continue
        a, b = (s.strip() for s in key.split(" vs ", 1))
        fk = frozenset((a, b))
        tags = []
        if a not in tg:
            tags.append(f"UNKNOWN TEAM '{a}'")
        if b not in tg:
            tags.append(f"UNKNOWN TEAM '{b}'")
        if not tags:
            if tg[a] != tg[b]:
                tags.append(f"CROSS-GROUP ({tg[a]} vs {tg[b]}) — not a group fixture")
            elif fk not in fixtures:
                tags.append("NO SUCH SCHEDULED FIXTURE")
        if fk in seen:
            tags.append("DUPLICATE")
        seen.add(fk)
        if not (isinstance(score, list) and len(score) == 2
                and all(isinstance(x, int) and 0 <= x <= 15 for x in score)):
            tags.append(f"BAD SCORE {score}")
        if fk in fixtures and not tags:
            mid, date, sh, sa, md = fixtures[fk]
            orient = "" if (sh == a and sa == b) else "  (orientation reversed — auto-swapped in sims)"
            lines.append(f"  ✅ {key:<32} M{mid:<3} MD{md} {date}{orient}")
        else:
            problems += 1
            mid = f"M{fixtures[fk][0]}" if fk in fixtures else "M?"
            lines.append(f"  ❌ {key:<32} {mid:<4} " + "; ".join(tags))
    return lines, problems


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/live_state.json"
    live_state = json.load(open(path, encoding="utf-8"))
    lines, problems = audit(live_state)
    print(f"Schedule cross-check of {path} ({len(lines)} result(s)):\n")
    print("\n".join(lines))
    print(f"\n{len(lines)} checked · {problems} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
