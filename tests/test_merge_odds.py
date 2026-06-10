"""Bulk odds-merger tests (S16): the integrity gates that make automated
import safe — a swapped column or wrong-year dataset must be QUARANTINED,
never silently written."""
import importlib.util
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
spec = importlib.util.spec_from_file_location(
    "merge_odds", os.path.join(REPO, "scripts", "merge_odds.py"))
mo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mo)

ELO = {"Spain": {"elo": 2100}, "Qatar": {"elo": 1400},
       "France": {"elo": 2050}, "Germany": {"elo": 1950},
       "South Korea": {"elo": 1750}, "Portugal": {"elo": 1990}}


def _template(*pairs):
    return [{"team_a": a, "team_b": b, "phase": ph,
             "odds_home": pre or "", "odds_draw": pre or "", "odds_away": pre or "",
             "bookmaker": "", "source_url": ""}
            for a, b, ph, pre in pairs]


class TestNameAndOrientation(unittest.TestCase):

    def test_alias_and_flipped_fixture_swaps_odds(self):
        # Raw uses "Korea Republic" and lists the fixture the other way round.
        raw = {("South Korea", "Portugal"): [(5.50, 4.00, 1.65)]}
        self.assertEqual(mo.canon("Korea Republic"), "South Korea")
        rows, filled, q, fuzzy, unmatched = mo.merge(
            _template(("Portugal", "South Korea", "GROUP", None)),
            raw, ELO, "test", "")
        self.assertEqual(filled, 1)
        self.assertEqual(q, [])
        # Flipped: home odds must become the raw AWAY price (Portugal 1.65)
        self.assertEqual(rows[0]["odds_home"], "1.65")
        self.assertEqual(rows[0]["odds_away"], "5.5")

    def test_filled_rows_are_never_touched(self):
        raw = {("Spain", "Qatar"): [(1.20, 7.00, 15.00)]}
        rows, filled, *_ = mo.merge(
            _template(("Spain", "Qatar", "GROUP", "9.99")), raw, ELO, "test", "")
        self.assertEqual(filled, 0)
        self.assertEqual(rows[0]["odds_home"], "9.99")

    def test_duplicate_raw_rows_collapse_to_median(self):
        raw = {("Spain", "Qatar"): [(1.20, 7.0, 15.0), (1.25, 6.8, 14.0), (1.22, 7.2, 16.0)]}
        rows, filled, q, *_ = mo.merge(
            _template(("Spain", "Qatar", "GROUP", None)), raw, ELO, "lbl", "")
        self.assertEqual(filled, 1)
        self.assertEqual(rows[0]["odds_home"], "1.22")     # median of 1.20/1.22/1.25
        self.assertIn("x3 median", rows[0]["bookmaker"])


class TestValidationGates(unittest.TestCase):

    def test_fat_finger_column_swap_is_quarantined_by_elo_gate(self):
        """THE case from the operational-risk argument: 1.20 and 15.00 swapped
        (700-Elo favourite priced as a 15.00 longshot) must be quarantined."""
        raw = {("Spain", "Qatar"): [(15.00, 7.00, 1.20)]}
        rows, filled, quarantine, *_ = mo.merge(
            _template(("Spain", "Qatar", "GROUP", None)), raw, ELO, "test", "")
        self.assertEqual(filled, 0)
        self.assertEqual(rows[0]["odds_home"], "")
        self.assertEqual(len(quarantine), 1)
        self.assertIn("swapped columns or wrong year", quarantine[0][1])

    def test_non_decimal_formats_quarantined_by_overround_window(self):
        # American-odds-like / percentage-like garbage -> book sum way off
        raw = {("France", "Germany"): [(150.0, 230.0, 180.0)]}
        rows, filled, quarantine, *_ = mo.merge(
            _template(("France", "Germany", "QF", None)), raw, ELO, "test", "")
        self.assertEqual(filled, 0)
        self.assertIn("book sum", quarantine[0][1])

    def test_sub_unity_odds_quarantined(self):
        raw = {("France", "Germany"): [(0.55, 0.28, 0.22)]}   # probabilities, not odds
        rows, filled, quarantine, *_ = mo.merge(
            _template(("France", "Germany", "QF", None)), raw, ELO, "test", "")
        self.assertEqual(filled, 0)
        self.assertIn("not decimal odds", quarantine[0][1])

    def test_plausible_close_match_passes_without_elo_complaint(self):
        # France vs Germany: 100-Elo gap, market mildly favours France — fine.
        raw = {("France", "Germany"): [(2.30, 3.30, 3.10)]}
        rows, filled, quarantine, *_ = mo.merge(
            _template(("France", "Germany", "QF", None)), raw, ELO, "test", "")
        self.assertEqual(filled, 1)
        self.assertEqual(quarantine, [])


class TestValidateOnly(unittest.TestCase):

    def test_manual_fat_finger_caught_in_filled_template(self):
        """The 1.35 -> 13.5 manual-entry case must fail --validate-only."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wc2099_odds.csv")
            with open(path, "w", encoding="utf-8") as f:
                f.write("team_a,team_b,phase,odds_home,odds_draw,odds_away,bookmaker,source_url\n"
                        "Spain,Qatar,GROUP,13.5,5.50,11.00,manual,\n"     # fat-fingered 1.35
                        "France,Germany,QF,2.30,3.30,3.10,manual,\n"      # fine
                        "Portugal,South Korea,GROUP,,,,\n")               # blank -> ignored
            n_filled, failures = mo.validate_filled_template(path, ELO)
            self.assertEqual(n_filled, 2)
            self.assertEqual(len(failures), 1)
            self.assertIn("Spain vs Qatar", failures[0][0])


class TestColumnDetection(unittest.TestCase):

    def test_autodetects_b365_and_kaggle_style_headers(self):
        home, away, odds = mo.detect_columns(
            ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "B365H", "B365D", "B365A"])
        self.assertEqual((home, away), ("HomeTeam", "AwayTeam"))
        self.assertEqual(odds, ("B365H", "B365D", "B365A"))

    def test_prefers_closing_columns_when_both_present(self):
        home, away, odds = mo.detect_columns(
            ["home_team", "away_team", "B365H", "B365D", "B365A", "PSCH", "PSCD", "PSCA"])
        self.assertEqual(odds, ("PSCH", "PSCD", "PSCA"))

    def test_unknown_headers_return_none(self):
        home, away, odds = mo.detect_columns(["foo", "bar", "baz"])
        self.assertIsNone(odds)


if __name__ == "__main__":
    unittest.main()
