#!/usr/bin/env python3
"""Read-only KO O/U-coinflip overlay: main KO tip vs the tendency-preserving O/U tip.

For a knockout round, `compute_ko_tip` gives the main model tip (+ lambda_adj + config)
in the official home/away orientation, and `ou_total_engine.ou_adjusted_from_extras`
re-slaves the goal TOTAL to the market's COIN-FLIP line (the interpolated O/U line where
P(over)=0.5) while PRESERVING the tip's tendency — a winner stays that winner (KO has no
draws under shootout_total). It fires only with sufficient per-line liquidity. Prints the
model tip and the O/U-adjusted tip side by side.

Backtest (T-45 market totals from the daemon logs): the tendency-preserving O/U scores
+1/6 in the KO and +1/31 in the group (vs -3 for the naive rescale that could flip a draw).

ISOLATION CONTRACT: read-only. Drives lambdas from prematch_alert.compute_ko_tip, applies
the O/U-coinflip re-slave, prints a side column. Mutates nothing; the main KO tips are
unaffected by this file. Sibling of fatigue_ko_tips.py / ou_total_tips.py (group).

Usage:
    python3 ou_ko_tips.py --round R32
    python3 ou_ko_tips.py --round R16 --odds-snapshot data/polymarket_match_odds.json
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import prematch_alert as pa                       # noqa: E402
import ou_total_engine as ou                      # noqa: E402

ROUND_STAGE = {"R32": "Round of 32", "R16": "Round of 16", "QF": "Quarter-final",
               "SF": "Semi-final", "F": "Final"}
# engine name -> odds-snapshot display name
ALIAS = {"Ivory Coast": "Côte d'Ivoire", "USA": "United States",
         "Bosnia": "Bosnia and Herzegovina", "Cape Verde": "Cabo Verde"}


def _desc(t):
    try:
        return t["TeamName"][0]["Description"]
    except Exception:
        return None


def round_fixtures(raw, stage_name):
    out = []
    for m in raw.get("Results", []):
        sn = m.get("StageName")
        if not (sn and stage_name in sn[0].get("Description", "")):
            continue
        h, a = pa.engine_name(_desc(m.get("Home"))), pa.engine_name(_desc(m.get("Away")))
        if not h or not a:
            continue                               # pairing not yet drawn
        out.append((m.get("Date"), h, a))
    out.sort()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Main KO tip vs tendency-preserving O/U-coinflip tip (isolated, read-only)")
    ap.add_argument("--round", required=True, choices=list(ROUND_STAGE))
    ap.add_argument("--odds-snapshot", default=None,
                    help="market snapshot (default: live refresh via prematch_alert)")
    args = ap.parse_args(argv)

    snap = args.odds_snapshot or pa.refresh_snapshot()
    extras = (json.load(open(snap)) or {}).get("extras", {})
    raw = pa._http_json(pa.CALENDAR_URL)
    fixtures = round_fixtures(raw, ROUND_STAGE[args.round])

    print(f"\nO/U-COINFLIP KO OVERLAY  —  {args.round}  "
          f"(tendenz-erhaltend; nur bei Linien-Liq ≥ {ou.OU_MIN_LINE_LIQUIDITY/1000:.0f}k)")
    print("=" * 104)
    if not fixtures:
        print(f"Keine {args.round}-Paarungen bekannt — die Runde ist noch nicht ausgelost.")
        return 0
    print(f"{'Match (official)':30}{'Modell':>7}  {'CFlinie':>8}{'liq':>7}  {'O/U-Tipp':>9}  Hinweis")
    print("-" * 104)

    nshift = 0
    for _date, h, a in fixtures:
        row = pa.compute_ko_tip(h, a, args.round, snap)
        mt = row["optimal_tip"]
        ma, mb = int(mt.split(":")[0]), int(mt.split(":")[1])
        ex = extras.get(f"{ALIAS.get(h, h)}|{ALIAS.get(a, a)}")
        tip, meta = ou.ou_adjusted_from_extras(
            row["lambda_a_adj"], row["lambda_b_adj"], row["config"], ex, (ma, mb),
            ko_convention=row.get("ko_convention"), team_a=h, team_b=a)

        cf = "—" if meta["coinflip_line"] is None else f"{meta['coinflip_line']}"
        liqs = "—" if meta["liq"] is None else f"{meta['liq']/1000:.0f}k"
        if not meta["eligible"]:
            outip, hint = "—", ("⛔ keine O/U-Linie" if meta["coinflip_line"] is None
                                else "⛔ Liq zu dünn → kein Reslave")
        else:
            outip = f"{tip[0]}:{tip[1]}"
            if meta["shifted"]:
                hint = f"→ SHIFT {mt}→{outip}"
                nshift += 1
            else:
                hint = "= Modell"
        print(f"{h + ' vs ' + a:30}{mt:>7}  {cf:>8}{liqs:>7}  {outip:>9}  {hint}")

    print("-" * 104)
    print(f"{len(fixtures)} Spiele; {nshift} O/U-Shift(s). Tendenz bleibt IMMER fix "
          f"(Sieger unverändert) — nur die Torzahl wird aufs Coinflip-Total re-slaved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
