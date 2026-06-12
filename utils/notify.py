"""WhatsApp push notifications via CallMeBot (free personal-use API).

One-time setup (per phone): add the CallMeBot bot number to your WhatsApp
contacts and send it the message "I allow callmebot to send me messages".
The bot replies with your personal apikey. Then export:

    CALLMEBOT_PHONE='+4917xxxxxxxx'   # your own number, with country code
    CALLMEBOT_APIKEY='123456'

Design rules (ops loop safety):
  - send_whatsapp() NEVER raises — a failed/unconfigured notification must
    not kill a scan or scoring run. It returns True/False and logs to stderr.
  - Unconfigured (missing env vars) is a silent no-op returning False, so
    every call site can be unconditional and tests stay network-free.
  - The container egress allowlist must include api.callmebot.com (it is
    blocked by default here, like the odds hosts — run on the ops machine
    or extend the allowlist).
"""
import os
import sys
import urllib.parse
import urllib.request

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
MAX_TEXT_LEN = 1400          # keep well under WhatsApp/CallMeBot practical limits
_TIMEOUT_S = 10

PHONE_ENV = "CALLMEBOT_PHONE"
APIKEY_ENV = "CALLMEBOT_APIKEY"


def is_configured() -> bool:
    return bool(os.environ.get(PHONE_ENV)) and bool(os.environ.get(APIKEY_ENV))


def send_whatsapp(text: str, phone: str = None, apikey: str = None) -> bool:
    """POST-free GET to CallMeBot. Returns True iff the API answered 2xx.

    phone/apikey default to the CALLMEBOT_PHONE / CALLMEBOT_APIKEY env vars;
    with neither configured this is a no-op returning False (no network I/O).
    """
    phone = phone or os.environ.get(PHONE_ENV)
    apikey = apikey or os.environ.get(APIKEY_ENV)
    if not phone or not apikey:
        return False
    text = (text or "").strip()
    if not text:
        return False
    if len(text) > MAX_TEXT_LEN:
        text = text[: MAX_TEXT_LEN - 1] + "…"

    url = CALLMEBOT_URL + "?" + urllib.parse.urlencode(
        {"phone": phone, "text": text, "apikey": apikey})
    req = urllib.request.Request(url, headers={"User-Agent": "wm2026-predictor-ops"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                sys.stderr.write(f"[notify] CallMeBot HTTP {resp.status}\n")
            return ok
    except Exception as e:                       # noqa: BLE001 — must never raise
        sys.stderr.write(f"[notify] WhatsApp send failed: {e}\n")
        return False


def format_edges_message(entries: list, max_legs: int = 3) -> str:
    """Compact one-message summary of an edge-scanner result set."""
    if not entries:
        return ""
    lines = [f"WM2026 scanner: {len(entries)} paper edge(s)"]
    for e in entries[:max_legs]:
        lines.append(f"• {e['market']} / {e['team']}: odds {e['odds']:.2f}, "
                     f"edge {e['edge'] * 100:+.1f}%, stake {e['stake'] * 100:.2f}%")
    if len(entries) > max_legs:
        lines.append(f"… +{len(entries) - max_legs} more")
    lines.append(f"Σ stake {sum(e['stake'] for e in entries) * 100:.2f}% bankroll (paper)")
    return "\n".join(lines)
