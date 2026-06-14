"""WhatsApp/CallMeBot notifier tests — offline, no network.

urllib.request.urlopen is monkeypatched throughout; the unconfigured path is
asserted to perform NO network I/O at all (the ops-loop safety contract of
utils/notify.py: never raise, no-op without CALLMEBOT_* env vars).
"""
import os
import sys
import unittest
import urllib.parse
from unittest import mock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils import notify
from edge_scanner import EdgeScanner


class _Resp:
    def __init__(self, status=200, body=b"Message queued. You will receive it in a few seconds."):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _entry(market="Outright", team="Spain", odds=6.5, edge=0.03, stake=0.012, p_fair=0.15, p_mod=0.18):
    return {"market": market, "team": team, "odds": odds, "edge": edge,
            "stake": stake, "p_fair": p_fair, "p_mod": p_mod, "ev": edge}


class TestSendWhatsapp(unittest.TestCase):
    def setUp(self):
        # Isolate from any real ops configuration on the host.
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(notify.PHONE_ENV, None)
        os.environ.pop(notify.APIKEY_ENV, None)
        os.environ.pop(notify.RECIPIENTS_ENV, None)

    def tearDown(self):
        self._env.stop()

    def test_unconfigured_is_noop_without_network(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=AssertionError("network I/O attempted")) as m:
            self.assertFalse(notify.send_whatsapp("hello"))
            m.assert_not_called()
        self.assertFalse(notify.is_configured())

    def test_empty_text_is_noop(self):
        with mock.patch("urllib.request.urlopen") as m:
            self.assertFalse(notify.send_whatsapp("   ", phone="+491700", apikey="k"))
            m.assert_not_called()

    def test_configured_via_env_sends_urlencoded(self):
        os.environ[notify.PHONE_ENV] = "+491701234567"
        os.environ[notify.APIKEY_ENV] = "secret123"
        self.assertTrue(notify.is_configured())
        with mock.patch("urllib.request.urlopen", return_value=_Resp()) as m:
            self.assertTrue(notify.send_whatsapp("MD1: 4 pts & Glück +0.63"))
        req = m.call_args[0][0]
        url = req.full_url
        self.assertTrue(url.startswith(notify.CALLMEBOT_URL + "?"))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["phone"], ["+491701234567"])
        self.assertEqual(q["apikey"], ["secret123"])
        self.assertEqual(q["text"], ["MD1: 4 pts & Glück +0.63"])  # round-trips the urlencoding

    def test_args_override_env_and_http_error_returns_false(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            # must not raise — ops-loop contract
            self.assertFalse(notify.send_whatsapp("x", phone="+1", apikey="k"))

    def test_multiple_recipients_all_receive(self):
        os.environ[notify.RECIPIENTS_ENV] = "49170000001:111111,49170000002:222222"
        self.assertTrue(notify.is_configured())
        sent_urls = []

        def grab(req, timeout=None):
            sent_urls.append(req.full_url)
            return _Resp()

        with mock.patch("urllib.request.urlopen", side_effect=grab):
            self.assertTrue(notify.send_whatsapp("hallo"))
        self.assertEqual(len(sent_urls), 2)
        qs = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query) for u in sent_urls]
        self.assertEqual({q["phone"][0] for q in qs}, {"49170000001", "49170000002"})
        self.assertEqual({q["apikey"][0] for q in qs}, {"111111", "222222"})

    def test_phone_env_plus_recipients_deduplicated(self):
        os.environ[notify.PHONE_ENV] = "49170000001"
        os.environ[notify.APIKEY_ENV] = "111111"
        os.environ[notify.RECIPIENTS_ENV] = "49170000001:111111,49170000002:222222"
        with mock.patch("urllib.request.urlopen", return_value=_Resp()) as m:
            self.assertTrue(notify.send_whatsapp("hallo"))
        self.assertEqual(m.call_count, 2)        # not 3 — duplicate pair collapsed

    def test_partial_failure_still_counts_as_delivered(self):
        os.environ[notify.RECIPIENTS_ENV] = "1:a,2:b"
        calls = iter([OSError("boom"), _Resp()])

        def flaky(req, timeout=None):
            r = next(calls)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch("urllib.request.urlopen", side_effect=flaky):
            self.assertTrue(notify.send_whatsapp("x"))   # one of two landed

    def test_all_recipients_failing_returns_false(self):
        os.environ[notify.RECIPIENTS_ENV] = "1:a,2:b"
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertFalse(notify.send_whatsapp("x"))

    def test_explicit_args_send_to_single_recipient_only(self):
        os.environ[notify.RECIPIENTS_ENV] = "1:a,2:b"
        with mock.patch("urllib.request.urlopen", return_value=_Resp()) as m:
            self.assertTrue(notify.send_whatsapp("x", phone="+9", apikey="k"))
        self.assertEqual(m.call_count, 1)
        self.assertIn("phone=%2B9", m.call_args[0][0].full_url)

    def test_http200_with_error_body_is_failure(self):
        # CallMeBot returns 200 even when it rejects — the body carries the truth.
        with mock.patch("urllib.request.urlopen",
                        return_value=_Resp(body=b"ApiKey 000000 is not valid for the phone 49xxx...")):
            self.assertFalse(notify.send_whatsapp("x", phone="+1", apikey="k"))

    def test_http200_with_success_body_is_delivery(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=_Resp(body=b"Message queued. You will receive it in a few seconds.")):
            self.assertTrue(notify.send_whatsapp("x", phone="+1", apikey="k"))

    def test_long_text_truncated(self):
        captured = {}

        def grab(req, timeout=None):
            captured["url"] = req.full_url
            return _Resp()

        with mock.patch("urllib.request.urlopen", side_effect=grab):
            self.assertTrue(notify.send_whatsapp("A" * 5000, phone="+1", apikey="k"))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        self.assertEqual(len(q["text"][0]), notify.MAX_TEXT_LEN)
        self.assertTrue(q["text"][0].endswith("…"))


class TestFormatEdgesMessage(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(notify.format_edges_message([]), "")

    def test_caps_legs_and_sums_stake(self):
        entries = [_entry(team=f"T{i}", stake=0.01) for i in range(5)]
        msg = notify.format_edges_message(entries, max_legs=3)
        self.assertIn("5 paper edge(s)", msg)
        self.assertIn("… +2 more", msg)
        self.assertIn("Σ stake 5.00% bankroll (paper)", msg)
        self.assertEqual(msg.count("•"), 3)


class TestScannerNotifyDedup(unittest.TestCase):
    """_maybe_notify contract on a bare instance (no matrix, no boot)."""

    def _scanner(self, notify_on=True):
        sc = EdgeScanner.__new__(EdgeScanner)
        sc.notify = notify_on
        sc._last_notified_legs = None
        return sc

    def test_disabled_never_sends(self):
        sc = self._scanner(notify_on=False)
        with mock.patch("edge_scanner.wa_notify.send_whatsapp") as m:
            sc._maybe_notify([_entry()])
            m.assert_not_called()

    def test_sends_once_then_dedups_then_reports_disappearance(self):
        sc = self._scanner()
        with mock.patch("edge_scanner.wa_notify.send_whatsapp", return_value=True) as m:
            sc._maybe_notify([_entry()])          # new edge -> send
            sc._maybe_notify([_entry()])          # same set -> silent
            self.assertEqual(m.call_count, 1)
            sc._maybe_notify([])                  # edges gone -> send
            self.assertEqual(m.call_count, 2)
            self.assertIn("gone", m.call_args[0][0])
            sc._maybe_notify([])                  # still gone -> silent
            self.assertEqual(m.call_count, 2)

    def test_empty_first_scan_stays_silent(self):
        sc = self._scanner()
        with mock.patch("edge_scanner.wa_notify.send_whatsapp") as m:
            sc._maybe_notify([])
            m.assert_not_called()

    def test_failed_send_retries_next_scan(self):
        sc = self._scanner()
        with mock.patch("edge_scanner.wa_notify.send_whatsapp", return_value=False) as m:
            sc._maybe_notify([_entry()])
            sc._maybe_notify([_entry()])          # not deduped: first send failed
            self.assertEqual(m.call_count, 2)


if __name__ == "__main__":
    unittest.main()
