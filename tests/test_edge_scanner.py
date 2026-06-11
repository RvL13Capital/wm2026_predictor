"""Edge scanner unit tests (plan step S17) — offline, no network, no matrix build.

A stub matrix (team indexing only, no tensors) is injected so the pure
evaluation pipeline — de-vig → edge flagging → JOINT Kelly sizing → risk caps
→ ledger — is tested without the ~4-minute precompute or any live fetch.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np

import predictor
import tournament_bonusfragen as tb
from edge_scanner import EdgeScanner
from vectorized_mc import MatrixPrecomputer
from utils.math_utils import devig_book, kelly_mutually_exclusive


def _stub_matrix():
    """Team/fixture indexing without building any tensors."""
    mx = MatrixPrecomputer.__new__(MatrixPrecomputer)
    mx._init_team_index()
    return mx


def _scanner(tmpdir, **kw):
    defaults = dict(edge_threshold=0.015, kelly_fraction=0.25,
                    max_market_frac=0.05, max_total_frac=0.20,
                    ledger_path=os.path.join(tmpdir, "ledger.jsonl"),
                    matrix=_stub_matrix(), apply_adjustments=False)
    defaults.update(kw)
    return EdgeScanner(**defaults)


class TestOutrightEvaluation(unittest.TestCase):

    def test_joint_sizing_and_devig(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            book = {"Spain": 6.50, "Argentina": 7.00, "France": 7.50, "Field": 1.45}
            probs = np.zeros(sc.matrix.N_TEAMS)
            # Inflate model probs for Spain & Argentina, deflate France
            probs[sc.matrix.team_to_id["Spain"]] = 0.22
            probs[sc.matrix.team_to_id["Argentina"]] = 0.19
            probs[sc.matrix.team_to_id["France"]] = 0.05

            entries = sc.evaluate_outright(book, probs)
            teams = {e["team"] for e in entries}
            self.assertEqual(teams, {"Spain", "Argentina"})
            self.assertTrue(all(e["team"] != "Field" for e in entries))

            # Fair probs must be the Shin de-vig of the FULL book (incl. Field)
            order = list(book.keys())
            fair = devig_book([1.0 / book[t] for t in order], method="shin")
            fair_map = dict(zip(order, fair))
            for e in entries:
                self.assertAlmostEqual(e["p_fair"], fair_map[e["team"]], places=10)
                self.assertGreater(e["edge"], sc.edge_threshold)
                self.assertGreater(e["ev"], 0.0)

            # Stakes must equal joint Kelly over exactly the flagged legs
            flagged = sorted(entries, key=lambda x: x["team"])
            expect = kelly_mutually_exclusive(
                [e["p_mod"] for e in flagged], [e["odds"] for e in flagged], fraction=0.25)
            for e, s in zip(flagged, expect):
                self.assertAlmostEqual(e["stake_raw"], s, places=12)

    def test_no_edge_no_entries(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            book = {"Spain": 6.50, "Field": 1.20}
            probs = np.zeros(sc.matrix.N_TEAMS)
            probs[sc.matrix.team_to_id["Spain"]] = 0.10   # below fair
            self.assertEqual(sc.evaluate_outright(book, probs), [])


class TestMatchBookEvaluation(unittest.TestCase):

    def test_match_book_edges_and_joint_sizing(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            books = {"Mexico|South Africa": {"1": 1.60, "X": 4.50, "2": 8.00,
                                             "liquidity": 50000.0}}
            model = lambda a, b: (0.75, 0.15, 0.10)
            entries = sc.evaluate_match_books(books, model_1x2_fn=model)
            self.assertEqual(len(entries), 1)
            e = entries[0]
            self.assertIn("Mexico (1)", e["team"])
            fair = devig_book([1/1.60, 1/4.50, 1/8.00], method="shin")
            self.assertAlmostEqual(e["p_fair"], fair[0], places=10)
            self.assertAlmostEqual(e["p_mod"], 0.75)
            expect = kelly_mutually_exclusive([0.75], [1.60], fraction=0.25)[0]
            self.assertAlmostEqual(e["stake_raw"], expect, places=12)

    def test_thin_book_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            books = {"Mexico|South Africa": {"1": 1.60, "X": 4.50, "2": 8.00,
                                             "liquidity": 10.0}}   # below floor
            entries = sc.evaluate_match_books(books, model_1x2_fn=lambda a, b: (0.75, 0.15, 0.10))
            self.assertEqual(entries, [])

    def test_unknown_team_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            books = {"Atlantis|South Africa": {"1": 1.60, "X": 4.50, "2": 8.00,
                                               "liquidity": 50000.0}}
            entries = sc.evaluate_match_books(books, model_1x2_fn=lambda a, b: (0.9, 0.05, 0.05))
            self.assertEqual(entries, [])


class TestManualBooks(unittest.TestCase):

    def test_binary_reach_line(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            model_probs = {"sf": np.zeros(sc.matrix.N_TEAMS)}
            model_probs["sf"][sc.matrix.team_to_id["Spain"]] = 0.55
            manual = [{"name": "Reach SF", "kind": "binary", "margin": 0.05,
                       "book": {"Spain": 2.80}}]
            entries = sc.evaluate_manual_books(manual, model_probs)
            self.assertEqual(len(entries), 1)
            e = entries[0]
            pi_yes = 1 / 2.80
            pi_no = 1.05 - pi_yes
            fair_yes = devig_book([pi_yes, pi_no], method="shin")[0]
            self.assertAlmostEqual(e["p_fair"], fair_yes, places=10)
            self.assertAlmostEqual(
                e["stake_raw"], kelly_mutually_exclusive([0.55], [2.80], fraction=0.25)[0],
                places=12)


class TestRiskCapsAndLedger(unittest.TestCase):

    def test_per_leg_and_global_caps(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td, max_market_frac=0.05, max_total_frac=0.10)
            entries = [{"stake_raw": 0.20, "stake": 0.0},
                       {"stake_raw": 0.08, "stake": 0.0},
                       {"stake_raw": 0.02, "stake": 0.0}]
            capped = sc.apply_risk_caps(entries)
            # per-leg: 0.05, 0.05, 0.02 → total 0.12 > 0.10 → scale by 10/12
            self.assertAlmostEqual(capped[0]["stake"], 0.05 * (0.10 / 0.12), places=12)
            self.assertAlmostEqual(capped[1]["stake"], 0.05 * (0.10 / 0.12), places=12)
            self.assertAlmostEqual(capped[2]["stake"], 0.02 * (0.10 / 0.12), places=12)
            self.assertAlmostEqual(sum(e["stake"] for e in capped), 0.10, places=12)

    def test_ledger_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            entries = [{"market": "Outright Winner", "team": "Spain", "odds": 6.5,
                        "p_fair": 0.14, "p_mod": 0.20, "edge": 0.06, "ev": 0.30,
                        "stake_raw": 0.03, "stake": 0.03}]
            sc.write_ledger(entries, {"ts": "T", "mode": "paper"})
            with open(sc.ledger_path, encoding="utf-8") as f:
                rec = json.loads(f.readline())
            self.assertEqual(rec["mode"], "paper")
            self.assertEqual(rec["entries"][0]["team"], "Spain")


class TestModelMatch1x2(unittest.TestCase):

    def test_pure_prior_for_group_fixture(self):
        """Offline: real group fixture through the pure-model path (no market)."""
        with tempfile.TemporaryDirectory() as td:
            sc = _scanner(td)
            p_h, p_d, p_a = sc.model_match_1x2("Mexico", "South Africa")
            self.assertAlmostEqual(p_h + p_d + p_a, 1.0, places=6)
            self.assertGreater(p_h, p_a)        # host + Elo favourite
            self.assertGreater(p_d, 0.02)       # 90' grid retains draws


if __name__ == "__main__":
    unittest.main()
