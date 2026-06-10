"""Offline tests for the Odds-API historical filler (S16) — canned snapshots,
no network, no key. The pure core (closing-book selection) is what matters:
the LAST snapshot strictly before kickoff wins; post-kickoff snapshots never
count; medians across bookmakers; canonical name keys."""
import importlib.util
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
spec = importlib.util.spec_from_file_location(
    "fill_odds_theoddsapi", os.path.join(REPO, "scripts", "fill_odds_theoddsapi.py"))
fo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fo)


def _event(home, away, commence, books):
    return {
        "home_team": home, "away_team": away, "commence_time": commence,
        "bookmakers": [
            {"key": f"bk{i}", "markets": [{"key": "h2h", "outcomes": [
                {"name": home, "price": h}, {"name": "Draw", "price": d},
                {"name": away, "price": a}]}]}
            for i, (h, d, a) in enumerate(books)
        ],
    }


KICKOFF = "2022-11-22T10:00:00Z"


class TestClosingSelection(unittest.TestCase):

    def test_last_pre_kickoff_snapshot_wins(self):
        snapshots = [
            {"timestamp": "2022-11-21T10:00:00Z",
             "data": [_event("Argentina", "Saudi Arabia", KICKOFF, [(1.30, 5.5, 11.0)])]},
            {"timestamp": "2022-11-22T09:55:00Z",       # closing
             "data": [_event("Argentina", "Saudi Arabia", KICKOFF, [(1.25, 6.0, 14.0)])]},
            {"timestamp": "2022-11-22T11:00:00Z",       # in-play/after — must NOT count
             "data": [_event("Argentina", "Saudi Arabia", KICKOFF, [(9.99, 9.99, 1.01)])]},
        ]
        index = fo.closing_index_from_snapshots(snapshots)
        self.assertEqual(index[("Argentina", "Saudi Arabia")], [(1.25, 6.0, 14.0)])

    def test_median_across_bookmakers(self):
        snapshots = [{"timestamp": "2022-11-22T09:00:00Z",
                      "data": [_event("Argentina", "Saudi Arabia", KICKOFF,
                                      [(1.20, 6.0, 15.0), (1.25, 6.4, 13.0), (1.22, 6.2, 14.0)])]}]
        index = fo.closing_index_from_snapshots(snapshots)
        self.assertEqual(index[("Argentina", "Saudi Arabia")], [(1.22, 6.2, 14.0)])

    def test_event_only_seen_after_kickoff_is_omitted(self):
        snapshots = [{"timestamp": "2022-11-22T11:00:00Z",
                      "data": [_event("Argentina", "Saudi Arabia", KICKOFF, [(1.2, 6.0, 15.0)])]}]
        self.assertEqual(fo.closing_index_from_snapshots(snapshots), {})

    def test_api_team_names_canonicalized(self):
        snapshots = [{"timestamp": "2022-11-23T09:00:00Z",
                      "data": [_event("Korea Republic", "Uruguay",
                                      "2022-11-24T13:00:00Z", [(4.7, 3.5, 1.9)])]}]
        index = fo.closing_index_from_snapshots(snapshots)
        self.assertIn(("South Korea", "Uruguay"), index)

    def test_sweep_window_and_estimate(self):
        ts = fo.sweep_timestamps(2022, 12.0)
        self.assertEqual(ts[0], "2022-11-19T12:00:00Z")
        self.assertTrue(all(t.endswith("Z") for t in ts))
        self.assertGreater(len(ts), 50)
        self.assertLess(len(ts), 70)


if __name__ == "__main__":
    unittest.main()
