#!/usr/bin/env python3
"""Live group standings ("current group situation") from live_state.json (read-only, S20).

Computes each group's table — P W D L GF GA GD Pts — from the real results in live_state, plus
the qualification picture for the 48-team format: 12 group winners + 12 runners-up + the 8 best
third-placed teams advance to the Round of 32. Honest about partial data: shows games played, so a
half-complete group is obviously half-complete, not a final table.

Ordering within a group: Pts, then GD, then GF (the FIFA primary criteria). Head-to-head and the
fair-play/drawing-of-lots tail are NOT applied here — they need full results and are flagged when
they'd matter (teams level on all three). This is a situational read, not the official tiebreak.

    python3 scripts/group_standings.py [--live-state data/live_state.json] [--output ...]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tournament_bonusfragen as tbf


def _team_group():
    """team -> group letter."""
    tg = {}
    for g, teams in tbf.GROUPS.items():
        for t in teams:
            tg[t] = g
    return tg


def compute_tables(live_state):
    """Return {group: [row, ...]} sorted, where row has team/P/W/D/L/GF/GA/GD/Pts."""
    tg = _team_group()
    rows = {g: {t: {"team": t, "P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0}
                for t in teams} for g, teams in tbf.GROUPS.items()}
    for key, score in live_state.items():
        if " vs " not in key or not isinstance(score, list) or len(score) != 2:
            continue
        a, b = (s.strip() for s in key.split(" vs ", 1))
        if a not in tg or b not in tg or tg[a] != tg[b]:
            continue                      # not a group-stage pairing (KO, or cross-group typo)
        g = tg[a]
        ga, gb = int(score[0]), int(score[1])
        ra, rb = rows[g][a], rows[g][b]
        ra["P"] += 1; rb["P"] += 1
        ra["GF"] += ga; ra["GA"] += gb
        rb["GF"] += gb; rb["GA"] += ga
        if ga > gb:
            ra["W"] += 1; rb["L"] += 1; ra["Pts"] += 3
        elif ga < gb:
            rb["W"] += 1; ra["L"] += 1; rb["Pts"] += 3
        else:
            ra["D"] += 1; rb["D"] += 1; ra["Pts"] += 1; rb["Pts"] += 1
    out = {}
    for g, tbl in rows.items():
        lst = list(tbl.values())
        for r in lst:
            r["GD"] = r["GF"] - r["GA"]
        lst.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["team"]))
        out[g] = lst
    return out


def _level(a, b):
    """True if two rows are tied on all of Pts/GD/GF (where H2H / drawing of lots would decide)."""
    return a["Pts"] == b["Pts"] and a["GD"] == b["GD"] and a["GF"] == b["GF"]


def best_thirds(tables):
    """Rank the 12 third-placed teams; top 8 advance. Returns (ranked_rows, qualified_set)."""
    thirds = []
    for g, lst in tables.items():
        if len(lst) >= 3:
            r = dict(lst[2]); r["group"] = g
            thirds.append(r)
    thirds.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["team"]))
    qualified = {r["team"] for r in thirds[:8]}
    return thirds, qualified


def render(tables, live_state):
    tg = _team_group()
    played = sum(1 for k, v in live_state.items()
                 if " vs " in k and tg.get(k.split(" vs ")[0].strip()) ==
                 tg.get(k.split(" vs ")[1].strip()) and tg.get(k.split(" vs ")[0].strip()))
    L = []
    L.append("=" * 60)
    L.append(f"  WM 2026 — GROUP STANDINGS   ({played}/72 group games played)")
    L.append("=" * 60)
    L.append("  Top 2 per group + 8 best 3rd-place → Round of 32.  ✓=adv  ⊕=best-3rd")
    L.append("  Order: Pts·GD·GF (H2H/lots NOT applied; ⚠=teams level on all three).")
    L.append("")
    _, third_q = best_thirds(tables)
    for g in sorted(tables):
        lst = tables[g]
        L.append(f"── Group {g} " + "─" * 47)
        L.append(f"   {'#':<2}{'Team':<15}{'P':>2}{'W':>3}{'D':>2}{'L':>2}{'GF':>4}{'GA':>3}{'GD':>4}{'Pts':>4}")
        for i, r in enumerate(lst, 1):
            mark = "✓" if i <= 2 else ("⊕" if r["team"] in third_q else (" " if i == 3 else " "))
            warn = ""
            if i < len(lst) and _level(r, lst[i]):
                warn = " ⚠"
            L.append(f"   {i:<2}{r['team']:<15}{r['P']:>2}{r['W']:>3}{r['D']:>2}{r['L']:>2}"
                     f"{r['GF']:>4}{r['GA']:>3}{r['GD']:>+4}{r['Pts']:>4} {mark}{warn}")
        L.append("")
    # best-thirds board
    thirds, third_q = best_thirds(tables)
    if thirds:
        L.append("── Best 3rd-place race (top 8 advance) " + "─" * 21)
        for i, r in enumerate(thirds, 1):
            mark = "✓" if r["team"] in third_q else " "
            L.append(f"   {i:>2} {r['team']:<15} (Grp {r['group']})  "
                     f"Pts {r['Pts']} GD {r['GD']:+d} GF {r['GF']}  {mark}")
        L.append("")
    L.append("=" * 60)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Live group standings from live_state.json")
    ap.add_argument("--live-state", default="data/live_state.json")
    ap.add_argument("--output")
    args = ap.parse_args()
    with open(args.live_state, encoding="utf-8") as f:
        live_state = json.load(f)
    out = render(compute_tables(live_state), live_state)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"wrote {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
