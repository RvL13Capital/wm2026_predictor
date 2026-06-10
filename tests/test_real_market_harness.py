"""Plumbing tests for the gate-G2 harness (S16) — SYNTHETIC fixtures only.

These verify the join/orientation/ET-settlement/metric/betting mechanics of
backtest_real_market.py. They make NO claim about real market alpha: the gate
itself runs only on real closing-odds CSVs, which are not yet in the repo
(the script exits 2 'AWAITING DATA' until they are — also tested here).
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import backtest_real_market as brm

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

FAKE_ELO = {"Spain": {"elo": 2100}, "Qatar": {"elo": 1400},
            "France": {"elo": 2050}, "Germany": {"elo": 1950}}


def _fake_et(team_a, team_b, phase, year):
    # The France-Germany QF "went to extra time" in our synthetic history
    return phase != "GROUP" and {team_a, team_b} == {"France", "Germany"}


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TestLoadFold(unittest.TestCase):

    def _fold(self):
        td = tempfile.mkdtemp()
        _write(os.path.join(td, "results.csv"),
               "team_a,team_b,goals_a,goals_b,phase\n"
               "Spain,Qatar,3,0,GROUP\n"
               "France,Germany,2,1,QF\n")          # 2:1 AFTER ET (F9 convention)
        _write(os.path.join(td, "odds.csv"),
               "team_a,team_b,odds_home,odds_draw,odds_away,phase\n"
               "Spanien,Katar,1.30,5.50,11.00,GROUP\n"     # German spellings -> canon
               "Deutschland,Frankreich,3.10,3.30,2.40,QF\n")  # swapped orientation
        return brm.load_fold(2099, os.path.join(td, "odds.csv"),
                             os.path.join(td, "results.csv"), FAKE_ELO, _fake_et)

    def test_join_canonicalization_and_orientation(self):
        rows = self._fold()
        self.assertEqual(len(rows), 2)
        m = {(r["team_a"], r["team_b"]): r for r in rows}
        self.assertIn(("Spain", "Qatar"), m)
        # Swapped row re-oriented to the results order, odds H/A swapped with it
        fg = m[("France", "Germany")]
        self.assertEqual(fg["odds"], (2.40, 3.30, 3.10))

    def test_outcomes_group_and_ko_et_draw(self):
        rows = self._fold()
        m = {(r["team_a"], r["team_b"]): r for r in rows}
        self.assertEqual(m[("Spain", "Qatar")]["outcome"], 0)       # home win
        # KO game in the ET set: market settles the 90' as a DRAW even though
        # the recorded (after-ET) score is 2:1
        self.assertEqual(m[("France", "Germany")]["outcome"], 1)


class TestEvaluateFold(unittest.TestCase):

    def test_metrics_and_flat_betting_math(self):
        rows = [{"year": 2099, "team_a": "Spain", "team_b": "Qatar",
                 "phase": "GROUP", "odds": (2.00, 3.50, 4.00), "outcome": 0,
                 "elo_a": 2100, "elo_b": 1400}]
        res = brm.evaluate_fold(rows, threshold=0.02, kelly_fraction=0.25)
        self.assertEqual(res["n"], 1)
        # A 700-Elo favourite at evens is a huge model edge -> exactly one
        # flat bet on home, which wins +1.0 (odds 2.00)
        self.assertEqual(res["n_bets"], 1)
        self.assertAlmostEqual(res["flat_roi"], 1.0)
        self.assertGreater(res["kelly_final_bankroll"], 100.0)
        for name in ("market", "model", "blend"):
            for metric, val in res["metrics"][name].items():
                self.assertTrue(0.0 <= val < 10.0, f"{name}.{metric}={val}")
        # Model must be MORE confident in the favourite than the de-vigged market
        self.assertLess(res["metrics"]["model"]["logloss"],
                        res["metrics"]["market"]["logloss"])

    def test_gate_verdict_logic(self):
        good = {"metrics": {"market": {"logloss": 1.00},
                            "model": {"logloss": 0.90}, "blend": {"logloss": 0.95}}}
        bad = {"metrics": {"market": {"logloss": 1.00},
                           "model": {"logloss": 1.10}, "blend": {"logloss": 1.05}}}
        wins = [1.0] * 200    # ROI CI clearly > 0
        passed, reasons, (lo, hi) = brm.gate_verdict({1: good, 2: good, 3: bad}, wins)
        self.assertTrue(passed)
        self.assertGreater(lo, 0.0)
        passed2, _, _ = brm.gate_verdict({1: good, 2: bad, 3: bad}, wins)
        self.assertFalse(passed2)                       # (a) fails
        losses = [-1.0, 1.0] * 100
        passed3, _, _ = brm.gate_verdict({1: good, 2: good, 3: bad}, losses)
        self.assertFalse(passed3)                       # (b) fails


class TestBlankTemplateTolerance(unittest.TestCase):

    def test_blank_and_invalid_odds_rows_are_skipped(self):
        td = tempfile.mkdtemp()
        _write(os.path.join(td, "results.csv"),
               "team_a,team_b,goals_a,goals_b,phase\n"
               "Spain,Qatar,3,0,GROUP\n"
               "France,Germany,2,1,QF\n")
        _write(os.path.join(td, "odds.csv"),
               "team_a,team_b,odds_home,odds_draw,odds_away,phase,bookmaker,source_url\n"
               "Spain,Qatar,1.30,5.50,11.00,GROUP,demo,\n"
               "France,Germany,,,,QF,,\n")              # template row, not filled yet
        rows = brm.load_fold(2099, os.path.join(td, "odds.csv"),
                             os.path.join(td, "results.csv"), FAKE_ELO, _fake_et)
        self.assertEqual(len(rows), 1)                   # only the completed row
        self.assertEqual(rows[0]["team_a"], "Spain")


class TestAwaitingData(unittest.TestCase):

    def test_exits_2_until_some_odds_rows_are_completed(self):
        """The committed odds CSVs start as blank fixture templates; the gate
        must keep reporting AWAITING DATA (exit 2) until rows are filled."""
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO, "backtest_real_market.py")],
            cwd=REPO, capture_output=True, text=True)
        if proc.returncode == 0:
            self.skipTest("real odds data present — gate is live")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("AWAITING DATA", proc.stdout)


if __name__ == "__main__":
    unittest.main()
