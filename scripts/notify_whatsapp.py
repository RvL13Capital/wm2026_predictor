#!/usr/bin/env python3
"""Send an ad-hoc WhatsApp message via CallMeBot (utils/notify.py).

Usage:
    python3 scripts/notify_whatsapp.py "MD1 sheet regenerated, 10 tips moved"
    python3 scripts/score_predictions.py | tail -3 | python3 scripts/notify_whatsapp.py

Reads the message from argv, or from stdin when no argument is given (so ops
summaries can be piped straight in). Requires CALLMEBOT_PHONE/CALLMEBOT_APIKEY;
exits 1 if unconfigured or the send fails, so cron jobs can detect it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import notify


def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read()
    if not text.strip():
        sys.exit("usage: notify_whatsapp.py <message>   (or pipe the message via stdin)")
    if not notify.is_configured():
        sys.exit(f"❌ not configured — export {notify.PHONE_ENV} and {notify.APIKEY_ENV} "
                 "(see utils/notify.py header for the one-time CallMeBot activation)")
    ok = notify.send_whatsapp(text)
    print("✅ sent" if ok else "❌ send failed (see stderr)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
