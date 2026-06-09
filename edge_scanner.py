# edge_scanner.py — Live Market Edge Scanner Daemon
#
# Compares the engine's simulated probabilities against market lines to flag
# +EV bets and size them with fractional Kelly.
#
# INTEGRITY NOTE (see validation/SHIN_EVALUATION.md):
#   The edge MUST be computed against the *de-vigged* market probability, not
#   the raw inverse-odds (which still contain the bookmaker overround). Earlier
#   this file used `edge = p_mod - 1/decimal_odds`, comparing a fair model
#   probability against a vig-inflated implied probability — a systematic bias
#   that manufactures or hides edge depending on market structure. Every book is
#   now de-vigged with utils.math_utils.devig_book before differencing:
#         edge = p_mod - p_mkt_devigged
#   Flagging uses the de-vigged edge; Kelly/EV sizing uses the *raw* decimal
#   odds (that is what actually gets paid).
#
# The built-in market lines below are ILLUSTRATIVE STATIC books, structured to
# be internally consistent (complete mutually-exclusive books with a "Field"
# bucket; two-sided binary reach lines). In production, replace
# `_fetch_market_books` with a live exchange feed of the same shape.

import time
import sys
import json
import argparse
import numpy as np
from datetime import datetime

import predictor
from vectorized_mc import MatrixPrecomputer, VectorizedSimulator
import tournament_bonusfragen as tb
from utils.math_utils import devig_book

# Assumed two-way margin for binary "reach stage" lines (only the YES price is
# quoted below; the complementary NO price is reconstructed at this margin so
# the book can be de-vigged honestly).
_REACH_MARGIN = 0.05


class EdgeScanner:
    def __init__(self, edge_threshold: float = 0.015, kelly_fraction: float = 0.25):
        """
        edge_threshold: Minimum (de-vigged) probability divergence to flag a bet (e.g. 1.5%).
        kelly_fraction: Fractional Kelly multiplier for bankroll safety (e.g. 1/4 Kelly).
        """
        self.edge_threshold = edge_threshold
        self.kelly_fraction = kelly_fraction
        self.N = 100000

        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] Booting High-Frequency Edge Scanner...\n")

        # Apply ELO adjustments to predictor.WORLD_CUP_2026_TEAMS
        if hasattr(tb, "INJURY_ELO_ADJUSTMENTS") and tb.INJURY_ELO_ADJUSTMENTS:
            sys.stdout.write("Applying injury Elo adjustments...\n")
            for team, adj in tb.INJURY_ELO_ADJUSTMENTS.items():
                if team in predictor.WORLD_CUP_2026_TEAMS:
                    predictor.WORLD_CUP_2026_TEAMS[team]["elo"] += adj
        if hasattr(tb, "compute_squad_elo_adjustments"):
            sys.stdout.write("Applying squad value & form Elo adjustments...\n")
            squad_adjustments = tb.compute_squad_elo_adjustments()
            for team, adj in squad_adjustments.items():
                if team in predictor.WORLD_CUP_2026_TEAMS:
                    predictor.WORLD_CUP_2026_TEAMS[team]["elo"] += adj

        self.matrix = MatrixPrecomputer(host_teams=tb.HOST_TEAMS)
        self.team_names = self.matrix.id_to_team

    # ------------------------------------------------------------------ #
    #  Market lines (ILLUSTRATIVE STATIC — replace with live feed)        #
    # ------------------------------------------------------------------ #
    def _fetch_market_books(self, market_type: str):
        """Return an internally consistent book for the chosen derivative market.

        Shapes by kind:
          * multinomial : {team: decimal_odds, ..., "Field": decimal_odds}
                          (one complete mutually-exclusive winner book)
          * grouped     : [ {team: odds, ..., "Field": odds}, ... ]
                          (one complete book per group)
          * binary      : {team: yes_decimal_odds}
                          (NO side reconstructed at _REACH_MARGIN)
        """
        if market_type == "outrights":
            # 12 favourites + Field bucket => booksum ~1.15 (realistic outright margin)
            return {
                "Spain": 6.50, "Argentina": 7.00, "France": 7.50, "Brazil": 8.00,
                "England": 8.50, "Germany": 11.00, "Portugal": 15.00, "Netherlands": 17.00,
                "Colombia": 26.00, "Uruguay": 34.00, "USA": 81.00, "Mexico": 101.00,
                "Field": 6.00,
            }
        elif market_type == "win_group":
            # One complete book per group (favourite, challenger, Field for the rest).
            return [
                {"Spain": 1.50, "Germany": 2.40, "Field": 4.50},
                {"Argentina": 1.40, "Mexico": 5.00, "Field": 4.00},
                {"France": 1.35, "USA": 6.00, "Field": 4.50},
                {"England": 1.45, "Colombia": 4.50, "Field": 4.50},
                {"Brazil": 1.30, "Uruguay": 5.00, "Field": 5.00},
            ]
        elif market_type == "reach_r16":
            return {
                "Spain": 1.15, "Argentina": 1.20, "France": 1.22, "Brazil": 1.18,
                "England": 1.25, "Germany": 1.30, "Portugal": 1.40, "Netherlands": 1.45,
                "Colombia": 1.65, "Uruguay": 1.80, "USA": 2.10, "Mexico": 2.30,
            }
        elif market_type == "reach_qf":
            return {
                "Spain": 1.70, "Argentina": 1.80, "France": 1.90, "Brazil": 1.60,
                "England": 2.10, "Germany": 2.20, "Portugal": 2.50, "Netherlands": 2.60,
                "Colombia": 3.40, "Uruguay": 4.00, "USA": 6.00, "Mexico": 7.00,
            }
        elif market_type == "reach_sf":
            return {
                "Spain": 2.80, "Argentina": 3.00, "France": 3.20, "Brazil": 2.90,
                "England": 3.80, "Germany": 4.00, "Portugal": 4.50, "Netherlands": 5.00,
                "Colombia": 7.00, "Uruguay": 9.00, "USA": 15.00, "Mexico": 21.00,
            }
        elif market_type == "reach_final":
            return {
                "Spain": 3.80, "Argentina": 4.00, "France": 4.20, "Brazil": 3.90,
                "England": 5.00, "Germany": 5.50, "Portugal": 6.50, "Netherlands": 7.50,
                "Colombia": 11.00, "Uruguay": 15.00, "USA": 34.00, "Mexico": 51.00,
            }
        return {}

    @staticmethod
    def _devig_market(kind: str, book):
        """De-vig a market book. Returns (fair_probs, raw_odds) keyed by team.

        'Field' buckets are used for de-vigging only and excluded from the output.
        """
        fair, odds = {}, {}
        if kind == "multinomial":
            teams = list(book.keys())
            implied = [1.0 / book[t] for t in teams]
            probs = devig_book(implied, method="shin")
            for t, p in zip(teams, probs):
                if t != "Field":
                    fair[t] = p
                    odds[t] = book[t]
        elif kind == "grouped":
            for group in book:
                teams = list(group.keys())
                implied = [1.0 / group[t] for t in teams]
                probs = devig_book(implied, method="shin")
                for t, p in zip(teams, probs):
                    if t != "Field":
                        fair[t] = p
                        odds[t] = group[t]
        elif kind == "binary":
            for t, yes_odds in book.items():
                pi_yes = 1.0 / yes_odds
                pi_no = max(1e-9, (1.0 + _REACH_MARGIN) - pi_yes)
                probs = devig_book([pi_yes, pi_no], method="shin")
                fair[t] = probs[0]
                odds[t] = yes_odds
        return fair, odds

    def calculate_kelly_stake(self, prob_model: float, decimal_odds: float) -> float:
        """Recommended bankroll fraction to wager using Fractional Kelly (raw payout odds)."""
        b = decimal_odds - 1.0
        q = 1.0 - prob_model
        if b <= 0:
            return 0.0
        kelly_pct = (b * prob_model - q) / b
        return max(0.0, kelly_pct * self.kelly_fraction)

    def scan_all_markets(self, live_state: dict = None):
        sys.stdout.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] Executing Vectorized Pricing Engine ({self.N:,} sims)...\n")

        sim = VectorizedSimulator(self.matrix, n_sims=self.N)
        start_time = time.time()
        g_winners, stage_reach, _, champs, _ = sim.simulate(live_state=live_state)
        calc_time = time.time() - start_time

        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] Pricing complete in {calc_time:.3f}s. Fetching market lines...\n")

        # --- Model probabilities per derivative ---
        counts = np.bincount(champs, minlength=self.matrix.N_TEAMS)
        probs_outright = counts / float(self.N)
        probs_r16 = np.mean(stage_reach >= 2, axis=0)
        probs_qf = np.mean(stage_reach >= 3, axis=0)
        probs_sf = np.mean(stage_reach >= 4, axis=0)
        probs_final = np.mean(stage_reach >= 5, axis=0)

        probs_wingroup = np.zeros(self.matrix.N_TEAMS)
        for g_idx, g_name in enumerate(self.matrix.group_names):
            winners = g_winners[:, g_idx]
            g_counts = np.bincount(winners, minlength=self.matrix.N_TEAMS)
            for t in tb.GROUPS[g_name]:
                t_id = self.matrix.team_to_id[t]
                probs_wingroup[t_id] = g_counts[t_id] / float(self.N)

        # (market label, kind, book, model-prob array)
        market_specs = [
            ("Outright Winner", "multinomial", self._fetch_market_books("outrights"), probs_outright),
            ("Reach R16",       "binary",      self._fetch_market_books("reach_r16"), probs_r16),
            ("Reach QF",        "binary",      self._fetch_market_books("reach_qf"),  probs_qf),
            ("Reach SF",        "binary",      self._fetch_market_books("reach_sf"),  probs_sf),
            ("Reach Final",     "binary",      self._fetch_market_books("reach_final"), probs_final),
            ("Win Group",       "grouped",     self._fetch_market_books("win_group"), probs_wingroup),
        ]

        scoreboard = []
        for mkt_name, kind, book, probs_array in market_specs:
            fair, odds = self._devig_market(kind, book)
            for team, p_fair in fair.items():
                if team not in self.matrix.team_to_id:
                    continue
                t_id = self.matrix.team_to_id[team]
                p_mod = float(probs_array[t_id])
                decimal_odds = odds[team]

                edge = p_mod - p_fair                       # de-vigged true edge
                ev = (p_mod * decimal_odds) - 1.0           # EV on raw payout odds

                if edge > self.edge_threshold and ev > 0:
                    stake = self.calculate_kelly_stake(p_mod, decimal_odds)
                    scoreboard.append({
                        "team": team,
                        "market": mkt_name,
                        "odds": decimal_odds,
                        "p_fair": p_fair,
                        "p_mod": p_mod,
                        "edge": edge,
                        "ev": ev,
                        "stake": stake,
                    })

        print("\n" + "=" * 109)
        print("📈 WORLD CUP 2026 DEEP DERIVATIVE SCOREBOARD  (edge vs. de-vigged market)")
        print("=" * 109)
        print(f"{'Market':<20} | {'Team':<15} | {'Odds':>8} | {'MktFair':>8} | {'Model':>8} | {'Edge':>8} | {'Rec. Stake':>10}")
        print("-" * 109)

        if not scoreboard:
            print("Status: No actionable edges found. Market is currently efficient (after de-vigging).")
        else:
            scoreboard.sort(key=lambda x: x["ev"], reverse=True)
            for item in scoreboard:
                print(f"🚨 {item['market']:<17} | {item['team']:<15} | {item['odds']:>8.2f} | "
                      f"{item['p_fair']*100:>7.1f}% | {item['p_mod']*100:>7.1f}% | "
                      f"{item['edge']*100:>+7.1f}% | {item['stake']*100:>9.2f}% Bnk")

        print("=" * 109)
        if scoreboard:
            print(f"Status: EDGE DETECTED. Execute fractional Kelly stakes ({self.kelly_fraction}x multiplier).")

    def run_daemon(self, interval_seconds: int = 60, live_state_path: str = None):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Daemon active. Scanning every {interval_seconds} seconds. Press Ctrl+C to abort.")
        try:
            while True:
                live_state = None
                if live_state_path:
                    try:
                        with open(live_state_path, 'r') as f:
                            live_state = json.load(f)
                    except Exception as e:
                        sys.stderr.write(f"⚠ Failed to reload live state: {e}\n")
                self.scan_all_markets(live_state=live_state)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nDaemon terminated by user.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live Market Edge Scanner Daemon")
    parser.add_argument("--threshold", type=float, default=0.015, help="Minimum de-vigged probability edge to trigger alert")
    parser.add_argument("--kelly", type=float, default=0.25, help="Fractional Kelly multiplier")
    parser.add_argument("--daemon", action="store_true", help="Run in continuous polling loop")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    parser.add_argument("--live-state", type=str, default=None, help="Path to live_state.json")
    args = parser.parse_args()

    scanner = EdgeScanner(edge_threshold=args.threshold, kelly_fraction=args.kelly)

    live_state = None
    if args.live_state:
        try:
            with open(args.live_state, 'r') as f:
                live_state = json.load(f)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Loaded live state with {len(live_state)} overrides.")
        except Exception as e:
            print(f"⚠ Failed to load live state: {e}")

    if args.daemon:
        scanner.run_daemon(interval_seconds=args.interval, live_state_path=args.live_state)
    else:
        scanner.scan_all_markets(live_state=live_state)
