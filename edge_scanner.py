# edge_scanner.py — Market Edge Scanner Daemon (PAPER MODE)
#
# Compares the engine's simulated probabilities against market lines to flag
# +EV bets and size them with simultaneous fractional Kelly.
#
# INTEGRITY NOTES (see validation/SHIN_EVALUATION.md and IMPLEMENTATION_PLAN.md S17):
#   * Edges are computed against the *de-vigged* market probability
#     (edge = p_mod − p_mkt_fair); Kelly/EV sizing uses the *raw* decimal odds
#     (that is what actually gets paid).
#   * Legs of one mutually exclusive book (outright winner, the 1/X/2 of a
#     match, a win-group book) are sized JOINTLY via
#     utils.math_utils.kelly_mutually_exclusive — independent per-leg Kelly is
#     not growth-optimal (tests/test_joint_kelly.py).
#   * Model 1X2 priors for match markets are PURE model (no market blending) —
#     blending the market into the prior and then differencing against the
#     same market would be self-referential.
#   * PAPER MODE ONLY: this tool prints and logs recommendations to a JSONL
#     ledger; there is deliberately NO order-execution path. Real-money use is
#     gated on the real-odds backtest verdict (plan gate G2, S16).
#
# Live sources:
#   * Outright winner book: Polymarket tournament-winner markets (near vig-free).
#   * Match 1X2 books: Polymarket per-game events (negRisk Yes/No legs), with
#     liquidity guards from odds_client.
#   * Derivative books (Reach R16/SF, Win Group, …): supplied via --books JSON
#     (no exchange carries them as clean books); the old built-in static demo
#     books were removed.

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np

import predictor
import tournament_bonusfragen as tb
from vectorized_mc import VectorizedSimulator, build_matrix
from utils.math_utils import devig_book, kelly_mutually_exclusive
from odds_client import PolymarketClient, THIN_LIQUIDITY

# Assumed two-way margin for manual binary "reach stage" lines (only the YES
# price is quoted; the NO side is reconstructed at this margin so the book can
# be de-vigged honestly).
_REACH_MARGIN = 0.05

# --------------------------------------------------------------------------- #
#  Two-track calibration (validation/SCORING_ENVIRONMENT_PRIOR.md, 2026-06-11)
#
#  Tips optimize POINTS and keep the frozen production λ (bg=1.0 — 299/192,
#  tests/test_lambda_points_floor.py). The scanner needs CALIBRATION: bg=1.25
#  was the log-loss LOTO pick on all three held-out folds
#  (validation/recalibration.txt) and reproduces real group-stage totals
#  (E[goals] 2.61 vs 2.62) and draw rate (21% vs 19%) where production claims
#  2.09 / 26%. Match-market pricing (model_match_1x2) runs under these
#  constants; the tournament matrix / Bonusfragen path is deliberately NOT
#  touched (it is the canonical pre-registered engine).
#
#  NOT a fix for everything: BTTS / exact-score cells saturate at ~34% BTTS
#  across the whole λ family vs 48% real — a structural biPoisson limitation
#  (no score-state dependence). Books on those cells are refused outright
#  (_STRUCTURALLY_UNPRICEABLE) until a state-dependent model exists.
# --------------------------------------------------------------------------- #
SCANNER_PRICING_CALIBRATION = {
    "elo_baseline_goals": 1.25,
    "elo_scale_factor": 1600.0,
}

# Manual-book name fragments the scanner refuses to price (see block above).
_STRUCTURALLY_UNPRICEABLE = ("btts", "both teams", "exact score", "correct score")


@contextmanager
def _calibrated_pricing():
    """Temporarily run predictor under the scanner's calibrated λ constants."""
    saved = {k: predictor.CONSTANTS[k] for k in SCANNER_PRICING_CALIBRATION}
    predictor.CONSTANTS.update(SCANNER_PRICING_CALIBRATION)
    try:
        yield
    finally:
        predictor.CONSTANTS.update(saved)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LEDGER = os.path.join(_PROJECT_ROOT, "scan_ledger", "2026.jsonl")


def _git_commit_label() -> str:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_PROJECT_ROOT,
                                         stderr=subprocess.STDOUT).decode().strip()
        if subprocess.call(["git", "diff", "--quiet"], cwd=_PROJECT_ROOT) != 0:
            commit += " (dirty)"
        return commit
    except Exception:
        return "unknown"


class EdgeScanner:
    def __init__(self, edge_threshold: float = 0.015, kelly_fraction: float = 0.25,
                 n_sims: int = 100000, max_market_frac: float = 0.05,
                 max_total_frac: float = 0.20, ledger_path: str = DEFAULT_LEDGER,
                 books_path: str = None, min_liquidity: float = THIN_LIQUIDITY,
                 matrix=None, apply_adjustments: bool = True):
        """
        edge_threshold:  minimum de-vigged probability divergence to flag a leg.
        kelly_fraction:  fractional Kelly multiplier (0.25 = quarter Kelly).
        max_market_frac: bankroll cap per single leg.
        max_total_frac:  bankroll cap on the sum of all open recommendations
                         in one scan (stakes scaled down proportionally).
        matrix:          inject a prebuilt MatrixPrecomputer (tests); built
                         via the S13 cache otherwise.
        """
        self.edge_threshold = edge_threshold
        self.kelly_fraction = kelly_fraction
        self.N = n_sims
        self.max_market_frac = max_market_frac
        self.max_total_frac = max_total_frac
        self.ledger_path = ledger_path
        self.books_path = books_path
        self.min_liquidity = min_liquidity
        self._group_contexts = None
        self._pm = None

        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] Booting Edge Scanner (paper mode)...\n")

        if apply_adjustments:
            # Apply ELO adjustments to predictor.WORLD_CUP_2026_TEAMS
            if hasattr(tb, "INJURY_ELO_ADJUSTMENTS") and tb.INJURY_ELO_ADJUSTMENTS:
                sys.stdout.write("Applying injury Elo adjustments...\n")
                for team, adj in tb.INJURY_ELO_ADJUSTMENTS.items():
                    if team in predictor.WORLD_CUP_2026_TEAMS:
                        predictor.WORLD_CUP_2026_TEAMS[team]["elo"] += adj
            if hasattr(tb, "compute_squad_elo_adjustments"):
                sys.stdout.write("Applying squad value & form Elo adjustments...\n")
                for team, adj in tb.compute_squad_elo_adjustments().items():
                    if team in predictor.WORLD_CUP_2026_TEAMS:
                        predictor.WORLD_CUP_2026_TEAMS[team]["elo"] += adj

        # Cached precompute (S13): warm scanner restarts in seconds, not minutes
        self.matrix = matrix if matrix is not None else build_matrix(host_teams=tb.HOST_TEAMS, verbose=True)
        self.team_names = self.matrix.id_to_team

    # ------------------------------------------------------------------ #
    #  Live market sources                                                #
    # ------------------------------------------------------------------ #
    def _polymarket(self) -> PolymarketClient:
        if self._pm is None:
            self._pm = PolymarketClient()
        return self._pm

    def fetch_outright_book(self):
        """Polymarket tournament-winner book as {team: decimal_odds}, or None.

        Polymarket prices are probabilities on a near-zero-margin exchange, so
        decimal odds = 1/p; de-vigging then reduces to proportional
        normalisation (devig_book handles that automatically)."""
        try:
            probs = self._polymarket().get_wc_winner_probabilities()
        except Exception as e:
            print(f"⚠ Outright fetch failed ({e}) — skipping outright market this scan.", file=sys.stderr)
            return None
        book = {}
        for name, p in probs.items():
            canon = predictor.TEAM_NAME_MAPPING.get(name.strip().lower(), name.strip())
            if p > 0.001:
                book[canon] = round(1.0 / p, 2)
        return book or None

    def fetch_match_books(self):
        """Polymarket per-match 1X2 books keyed 'A|B' (raw decimal odds +
        liquidity tags), thin lines dropped at the source."""
        try:
            data = self._polymarket().get_match_1x2_probabilities(min_liquidity=self.min_liquidity)
            return data.get("probabilities", {})
        except Exception as e:
            print(f"⚠ Match-book fetch failed ({e}) — skipping match markets this scan.", file=sys.stderr)
            return {}

    def load_manual_books(self):
        """Derivative books from --books JSON:
        {"books": [{"name": "Reach SF", "kind": "binary"|"multinomial"|"grouped",
                    "margin": 0.05?, "book": {...} | [{...}, ...]}]}"""
        if not self.books_path:
            return []
        try:
            with open(self.books_path, "r", encoding="utf-8") as f:
                return json.load(f).get("books", [])
        except Exception as e:
            print(f"⚠ Failed to load manual books {self.books_path}: {e}", file=sys.stderr)
            return []

    # ------------------------------------------------------------------ #
    #  Model probabilities                                                #
    # ------------------------------------------------------------------ #
    def model_tournament_probs(self, live_state: dict = None) -> dict:
        sim = VectorizedSimulator(self.matrix, n_sims=self.N)
        start_time = time.time()
        g_winners, stage_reach, _, champs, _ = sim.simulate(live_state=live_state)
        elapsed = time.time() - start_time

        counts = np.bincount(champs, minlength=self.matrix.N_TEAMS)
        probs = {
            "outright": counts / float(self.N),
            "r16": np.mean(stage_reach >= 2, axis=0),
            "qf": np.mean(stage_reach >= 3, axis=0),
            "sf": np.mean(stage_reach >= 4, axis=0),
            "final": np.mean(stage_reach >= 5, axis=0),
        }
        wingroup = np.zeros(self.matrix.N_TEAMS)
        for g_idx, g_name in enumerate(self.matrix.group_names):
            g_counts = np.bincount(g_winners[:, g_idx], minlength=self.matrix.N_TEAMS)
            for t in tb.GROUPS[g_name]:
                t_id = self.matrix.team_to_id[t]
                wingroup[t_id] = g_counts[t_id] / float(self.N)
        probs["wingroup"] = wingroup
        probs["_elapsed"] = elapsed
        return probs

    def model_match_1x2(self, team_a: str, team_b: str, phase: str = None):
        """PURE-model 90-minute 1X2 prior for one fixture (no market blending).

        Probabilities come from grid_90 regardless of phase, because exchange
        1X2 lines settle on the 90-minute result — for KO fixtures the
        (phase-adjusted) 90' grid is the correct comparison, NOT the
        shootout-total tipping grid."""
        if self._group_contexts is None:
            import schedule_context
            self._group_contexts, _ = schedule_context.get_group_match_contexts()

        row = {"team_a": team_a, "team_b": team_b}
        ctx = self._group_contexts.get((team_a, team_b))
        swapped = False
        if ctx is None:
            ctx = self._group_contexts.get((team_b, team_a))
            swapped = ctx is not None
        if ctx is not None:
            row["phase"] = "GROUP"
            for k, v in ctx.items():
                if swapped and k.endswith("_a"):
                    row[k[:-2] + "_b"] = str(v)
                elif swapped and k.endswith("_b"):
                    row[k[:-2] + "_a"] = str(v)
                else:
                    row[k] = str(v)
        else:
            row["phase"] = phase or "R32"

        form_a, form_b = tb.compute_xg_form_multipliers(team_a, team_b)
        row["form_a"] = str(form_a)
        row["form_b"] = str(form_b)
        if team_a in tb.HOST_TEAMS:
            row["status_a"] = "True Home"
            row["fan_pct_a"] = "0.70"
            row["fan_pct_b"] = "0.30"
        elif team_b in tb.HOST_TEAMS:
            row["status_b"] = "True Home"
            row["fan_pct_a"] = "0.30"
            row["fan_pct_b"] = "0.70"
        elev, accl_a, accl_b = tb._get_match_elevation(team_a, team_b)
        if elev > 1000:
            row["elevation"] = str(elev)
            row["accl_days_a"] = str(accl_a)
            row["accl_days_b"] = str(accl_b)

        with _calibrated_pricing():
            res = predictor.predict_single_match(row)
        grid_90 = res["grid_90"]
        p_h = p_d = p_a = 0.0
        for ga, inner in grid_90.items():
            for gb, p in inner.items():
                if ga > gb:
                    p_h += p
                elif ga == gb:
                    p_d += p
                else:
                    p_a += p
        tot = p_h + p_d + p_a
        if tot > 0:
            p_h, p_d, p_a = p_h / tot, p_d / tot, p_a / tot
        return p_h, p_d, p_a

    # ------------------------------------------------------------------ #
    #  Pure evaluation (no I/O — unit-testable)                           #
    # ------------------------------------------------------------------ #
    def _flag(self, p_mod: float, p_fair: float, odds: float) -> bool:
        return (p_mod - p_fair) > self.edge_threshold and (p_mod * odds - 1.0) > 0.0

    def _entries_from_exclusive_book(self, market_name: str, legs: list) -> list:
        """legs: [(label, decimal_odds, p_fair, p_mod), ...] of ONE mutually
        exclusive book. Flag by de-vigged edge; size flagged legs JOINTLY."""
        flagged = [(lbl, o, pf, pm) for (lbl, o, pf, pm) in legs if self._flag(pm, pf, o)]
        if not flagged:
            return []
        stakes = kelly_mutually_exclusive([pm for (_, _, _, pm) in flagged],
                                          [o for (_, o, _, _) in flagged],
                                          fraction=self.kelly_fraction)
        out = []
        for (lbl, o, pf, pm), stake in zip(flagged, stakes):
            out.append({
                "market": market_name, "team": lbl, "odds": o,
                "p_fair": pf, "p_mod": pm,
                "edge": pm - pf, "ev": pm * o - 1.0,
                "stake_raw": stake, "stake": stake,
            })
        return out

    def evaluate_outright(self, book: dict, probs_outright: np.ndarray) -> list:
        teams = list(book.keys())
        implied = [1.0 / book[t] for t in teams]
        fair = devig_book(implied, method="shin")
        legs = []
        for t, pf in zip(teams, fair):
            if t == "Field" or t not in self.matrix.team_to_id:
                continue
            pm = float(probs_outright[self.matrix.team_to_id[t]])
            legs.append((t, book[t], pf, pm))
        return self._entries_from_exclusive_book("Outright Winner", legs)

    def evaluate_manual_books(self, manual_books: list, model_probs: dict) -> list:
        """Manual derivative books. Binary reach lines size per leg (a binary
        book is its own exclusive book); multinomial/grouped books size jointly."""
        model_key = {"reach r16": "r16", "reach qf": "qf", "reach sf": "sf",
                     "reach final": "final", "win group": "wingroup",
                     "outright winner": "outright"}
        entries = []
        for spec in manual_books:
            name = spec.get("name", "?")
            kind = spec.get("kind")
            book = spec.get("book")
            if any(frag in name.strip().lower() for frag in _STRUCTURALLY_UNPRICEABLE):
                print(f"⛔ Manual book '{name}': REFUSED — BTTS/exact-score cells are structurally "
                      f"unpriceable by the biPoisson family (saturate ~34% BTTS vs 48% real; "
                      f"validation/SCORING_ENVIRONMENT_PRIOR.md). Not an edge source.", file=sys.stderr)
                continue
            arr = model_probs.get(model_key.get(name.strip().lower(), ""), None)
            if arr is None or book is None:
                print(f"⚠ Manual book '{name}': no matching model probabilities — skipped.", file=sys.stderr)
                continue
            if kind == "binary":
                margin = float(spec.get("margin", _REACH_MARGIN))
                for t, yes_odds in book.items():
                    if t not in self.matrix.team_to_id:
                        continue
                    pi_yes = 1.0 / yes_odds
                    pi_no = max(1e-9, (1.0 + margin) - pi_yes)
                    pf = devig_book([pi_yes, pi_no], method="shin")[0]
                    pm = float(arr[self.matrix.team_to_id[t]])
                    entries.extend(self._entries_from_exclusive_book(
                        name, [(t, yes_odds, pf, pm)]))
            elif kind == "multinomial":
                teams = list(book.keys())
                fair = devig_book([1.0 / book[t] for t in teams], method="shin")
                legs = [(t, book[t], pf, float(arr[self.matrix.team_to_id[t]]))
                        for t, pf in zip(teams, fair)
                        if t != "Field" and t in self.matrix.team_to_id]
                entries.extend(self._entries_from_exclusive_book(name, legs))
            elif kind == "grouped":
                for group_book in book:
                    teams = list(group_book.keys())
                    fair = devig_book([1.0 / group_book[t] for t in teams], method="shin")
                    legs = [(t, group_book[t], pf, float(arr[self.matrix.team_to_id[t]]))
                            for t, pf in zip(teams, fair)
                            if t != "Field" and t in self.matrix.team_to_id]
                    entries.extend(self._entries_from_exclusive_book(name, legs))
        return entries

    def evaluate_match_books(self, match_books: dict, model_1x2_fn=None) -> list:
        """Polymarket 1X2 books: one mutually exclusive 3-leg book per match."""
        model_1x2_fn = model_1x2_fn or self.model_match_1x2
        entries = []
        for key, line in match_books.items():
            if "|" not in key:
                continue
            name_a, name_b = key.split("|", 1)
            team_a = predictor.TEAM_NAME_MAPPING.get(name_a.strip().lower(), name_a.strip())
            team_b = predictor.TEAM_NAME_MAPPING.get(name_b.strip().lower(), name_b.strip())
            if team_a not in self.matrix.team_to_id or team_b not in self.matrix.team_to_id:
                continue
            if not all(k in line for k in ("1", "X", "2")):
                continue
            liq = float(line.get("liquidity", float("inf")))
            if liq < self.min_liquidity:
                continue
            odds = [float(line["1"]), float(line["X"]), float(line["2"])]
            fair = devig_book([1.0 / o for o in odds], method="shin")
            try:
                p_h, p_d, p_a = model_1x2_fn(team_a, team_b)
            except Exception as e:
                print(f"⚠ Model 1X2 failed for {team_a} vs {team_b}: {e}", file=sys.stderr)
                continue
            legs = [(f"{team_a} (1)", odds[0], fair[0], p_h),
                    (f"Draw ({team_a}/{team_b})", odds[1], fair[1], p_d),
                    (f"{team_b} (2)", odds[2], fair[2], p_a)]
            entries.extend(self._entries_from_exclusive_book(
                f"1X2 {team_a} vs {team_b}", legs))
        return entries

    def apply_risk_caps(self, entries: list) -> list:
        """Per-leg cap, then proportional scale-down to the global cap."""
        for e in entries:
            e["stake"] = min(e["stake_raw"], self.max_market_frac)
        total = sum(e["stake"] for e in entries)
        if total > self.max_total_frac and total > 0:
            scale = self.max_total_frac / total
            for e in entries:
                e["stake"] *= scale
        return entries

    # ------------------------------------------------------------------ #
    #  Ledger + scan orchestration                                        #
    # ------------------------------------------------------------------ #
    def write_ledger(self, entries: list, meta: dict):
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        record = dict(meta)
        record["entries"] = entries
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def scan_all_markets(self, live_state: dict = None, outright_book: dict = None,
                         match_books: dict = None, manual_books: list = None) -> list:
        sys.stdout.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] Executing Vectorized Pricing Engine ({self.N:,} sims)...\n")
        model_probs = self.model_tournament_probs(live_state=live_state)
        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] Pricing complete in {model_probs['_elapsed']:.3f}s. Fetching market lines...\n")

        if outright_book is None:
            outright_book = self.fetch_outright_book()
        if match_books is None:
            match_books = self.fetch_match_books()
        if manual_books is None:
            manual_books = self.load_manual_books()

        entries = []
        if outright_book:
            entries.extend(self.evaluate_outright(outright_book, model_probs["outright"]))
        if manual_books:
            entries.extend(self.evaluate_manual_books(manual_books, model_probs))
        if match_books:
            entries.extend(self.evaluate_match_books(match_books))

        entries = self.apply_risk_caps(entries)
        entries.sort(key=lambda x: x["ev"], reverse=True)

        meta = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": "paper",
            "commit": _git_commit_label(),
            "n_sims": self.N,
            "edge_threshold": self.edge_threshold,
            "kelly_fraction": self.kelly_fraction,
            "caps": {"per_market": self.max_market_frac, "total": self.max_total_frac},
            "pricing_calibration": dict(SCANNER_PRICING_CALIBRATION),
            "sources": {
                "outright": bool(outright_book),
                "match_books": len(match_books or {}),
                "manual_books": len(manual_books or []),
            },
        }
        self.write_ledger(entries, meta)

        print("\n" + "=" * 112)
        print("📈 WORLD CUP 2026 DERIVATIVE SCOREBOARD  (edge vs. de-vigged market — PAPER MODE)")
        print("=" * 112)
        print(f"{'Market':<28} | {'Leg':<24} | {'Odds':>7} | {'MktFair':>8} | {'Model':>7} | {'Edge':>7} | {'Stake':>9}")
        print("-" * 112)
        if not entries:
            print("Status: No actionable edges found. Market is currently efficient (after de-vigging).")
        else:
            for e in entries:
                print(f"🚨 {e['market']:<25} | {e['team']:<24} | {e['odds']:>7.2f} | "
                      f"{e['p_fair']*100:>7.1f}% | {e['p_mod']*100:>6.1f}% | "
                      f"{e['edge']*100:>+6.1f}% | {e['stake']*100:>7.2f}% Bnk")
        print("=" * 112)
        if entries:
            total = sum(e["stake"] for e in entries)
            print(f"Status: {len(entries)} paper recommendation(s), Σ stake {total*100:.2f}% bankroll "
                  f"(joint Kelly x{self.kelly_fraction}, caps {self.max_market_frac:.0%}/leg, "
                  f"{self.max_total_frac:.0%} total). Ledger: {os.path.relpath(self.ledger_path, _PROJECT_ROOT)}")
        return entries

    def run_daemon(self, interval_seconds: int = 60, live_state_path: str = None):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Daemon active (paper mode). Scanning every {interval_seconds}s. Ctrl+C to abort.")
        try:
            while True:
                live_state = None
                if live_state_path:
                    try:
                        with open(live_state_path, 'r') as f:
                            live_state = json.load(f)
                    except Exception as e:
                        sys.stderr.write(f"⚠ Failed to reload live state: {e}\n")
                try:
                    self.scan_all_markets(live_state=live_state)
                except Exception as e:
                    sys.stderr.write(f"⚠ Scan failed ({e}) — retrying next interval.\n")
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nDaemon terminated by user.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Edge Scanner Daemon (paper mode)")
    parser.add_argument("--threshold", type=float, default=0.015, help="Minimum de-vigged probability edge to flag")
    parser.add_argument("--kelly", type=float, default=0.25, help="Fractional Kelly multiplier")
    parser.add_argument("--sims", type=int, default=100000, help="Monte Carlo simulations per scan")
    parser.add_argument("--max-market", type=float, default=0.05, help="Bankroll cap per leg")
    parser.add_argument("--max-total", type=float, default=0.20, help="Bankroll cap per scan (all legs)")
    parser.add_argument("--min-liquidity", type=float, default=THIN_LIQUIDITY,
                        help="Skip match books with thinnest-leg liquidity below this (USD)")
    parser.add_argument("--books", type=str, default=None, help="Manual derivative books JSON")
    parser.add_argument("--ledger", type=str, default=DEFAULT_LEDGER, help="Paper scan ledger (JSONL)")
    parser.add_argument("--daemon", action="store_true", default=False, help="Run in continuous polling loop")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    parser.add_argument("--live-state", type=str, default=None, help="Path to live_state.json")
    args = parser.parse_args()

    scanner = EdgeScanner(edge_threshold=args.threshold, kelly_fraction=args.kelly,
                          n_sims=args.sims, max_market_frac=args.max_market,
                          max_total_frac=args.max_total, ledger_path=args.ledger,
                          books_path=args.books, min_liquidity=args.min_liquidity)

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
