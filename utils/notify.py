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
import re
import sys
import urllib.parse
import urllib.request

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
MAX_TEXT_LEN = 1400          # keep well under WhatsApp/CallMeBot practical limits
_TIMEOUT_S = 10

PHONE_ENV = "CALLMEBOT_PHONE"
APIKEY_ENV = "CALLMEBOT_APIKEY"
RECIPIENTS_ENV = "CALLMEBOT_RECIPIENTS"   # "phone:apikey[,phone:apikey…]" — additional recipients


def _norm_phone(p: str) -> str:
    """Normalize a phone to the bare international format CallMeBot accepts
    (digits only, no '+', no '00' trunk, no spaces/dashes). The bare form
    e.g. '491626410039' is the proven-good format; '+49…', '0049…', and
    spaced/dashed variants are all rejected as "format is incorrect"."""
    digits = re.sub(r"\D", "", (p or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def _recipients(phone: str = None, apikey: str = None) -> list:
    """Resolve the recipient list. Explicit phone+apikey args win (single
    recipient); otherwise CALLMEBOT_PHONE/APIKEY (one) plus every
    phone:apikey pair in CALLMEBOT_RECIPIENTS, deduplicated."""
    if phone and apikey:
        return [(_norm_phone(phone), apikey.strip())]
    out = []
    # Normalize phones + strip keys: an invisible trailing newline, a stray '+'
    # or '00' trunk in a GitHub Actions secret all make CallMeBot reject the
    # phone ("format is incorrect") even though the bare number works.
    p, k = _norm_phone(os.environ.get(PHONE_ENV, "")), (os.environ.get(APIKEY_ENV) or "").strip()
    if p and k:
        out.append((p, k))
    for pair in re.split(r"[,;]+", os.environ.get(RECIPIENTS_ENV, "").strip()):
        if ":" in pair:
            ph, key = pair.split(":", 1)
            ph, key = _norm_phone(ph), key.strip()
            if ph and key and (ph, key) not in out:
                out.append((ph, key))
    return out


def is_configured() -> bool:
    return bool(_recipients())


# CallMeBot's whatsapp.php returns HTTP 200 EVEN ON FAILURE, with the real
# status in the response BODY (e.g. "ApiKey is not valid", "You need to add the
# phone number…"). Checking only the status code reports rejected messages as
# sent — so we inspect the body too. Markers are matched case-insensitively.
_BODY_ERROR_MARKERS = (
    "not valid", "invalid", "is incorrect", "not registered", "you must",
    "you need to", "enable the api", "apikey is", "api key is", "error",
    "couldn't", "could not", "can't", "wasn't", "was not sent", "failed",
)
_BODY_SUCCESS_MARKERS = (
    "queued", "message sent", "will receive", "sent successfully",
    "message accepted", "successfully",
)


def _send_one(text: str, phone: str, apikey: str) -> bool:
    tail = phone[-4:] if phone else "????"
    url = CALLMEBOT_URL + "?" + urllib.parse.urlencode(
        {"phone": phone, "text": text, "apikey": apikey})
    req = urllib.request.Request(url, headers={"User-Agent": "wm2026-predictor-ops"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            ok = 200 <= resp.status < 300
            try:
                body = resp.read().decode("utf-8", "replace").strip()
            except Exception:                    # body unreadable — fall back to status only
                body = ""
            low = body.lower()
            # 200 + an error body = a rejected message, not a delivery.
            if ok and low:
                if any(m in low for m in _BODY_ERROR_MARKERS) and \
                        not any(m in low for m in _BODY_SUCCESS_MARKERS):
                    ok = False
            # Always surface what CallMeBot actually said — the only way to debug
            # non-delivery (the API lies via the body, not the status code).
            snippet = body[:180].replace("\n", " ") if body else "<empty body>"
            sys.stderr.write(f"[notify] …{tail} HTTP {resp.status} {'OK' if ok else 'REJECTED'}: {snippet}\n")
            return ok
    except Exception as e:                       # noqa: BLE001 — must never raise
        sys.stderr.write(f"[notify] WhatsApp send to …{tail} failed: {e}\n")
        return False


def send_whatsapp(text: str, phone: str = None, apikey: str = None) -> bool:
    """Send to every configured recipient. Returns True iff at least one send
    succeeded (the alert is considered delivered; per-recipient failures go to
    stderr). Unconfigured = no-op returning False with zero network I/O.
    """
    recipients = _recipients(phone, apikey)
    if not recipients:
        return False
    text = (text or "").strip()
    if not text:
        return False
    if len(text) > MAX_TEXT_LEN:
        text = text[: MAX_TEXT_LEN - 1] + "…"
    return any([_send_one(text, ph, key) for ph, key in recipients])


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
