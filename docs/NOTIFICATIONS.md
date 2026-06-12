# WhatsApp Ops Notifications (CallMeBot)

Push tournament-ops events to the operator's WhatsApp through the free
[CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/)
personal API. Implementation: `utils/notify.py` (stdlib-only, never raises,
silent no-op when unconfigured — safe to leave the flags on in cron).

## One-time activation (per phone)

1. Add the CallMeBot WhatsApp bot **+34 644 64 60 89** to your contacts
   (number current as of Jun 2026 — check callmebot.com if dead).
2. Send it the WhatsApp message: `I allow callmebot to send me messages`.
3. The bot replies with your personal apikey (if nothing arrives within
   2 minutes, retry after 24h).
4. Export on the ops machine:

```bash
export CALLMEBOT_PHONE='+4917xxxxxxxx'   # your number, with country code
export CALLMEBOT_APIKEY='123456'
```

**Never commit the apikey.** It is env-only by design; anyone with it can
message your WhatsApp.

## Hooks

```bash
# Edge scanner daemon: one push when the actionable edge set CHANGES
# (new edges, or previously flagged edges disappearing) — not every interval.
python3 edge_scanner.py --daemon --live-state data/live_state.json --notify

# Post-matchday scoring: push the TOTAL line (pts / expected / luck).
python3 scripts/score_predictions.py --results data/live_state.json --notify

# Ad-hoc / pipe (e.g. end of resim.sh or any cron step):
python3 scripts/notify_whatsapp.py "MD1 sheet v6 regenerated — 10 tips moved"
python3 scripts/score_predictions.py | tail -3 | python3 scripts/notify_whatsapp.py
```

## Recommendation-change alerts (always on)

The four recommendation-producing CLIs diff every run against the last
published recommendations (`utils/recommendations_state.py`, state in the
gitignored `data/recommendation_state.json`, override via `WM2026_REC_STATE`)
and alert — stderr always, WhatsApp when configured — listing exactly what
flipped, e.g. `Brazil vs Morocco: 0:0 → 1:0`:

| CLI | Scope | Alerts on |
|---|---|---|
| `matchday_tips.py` | `MD<n>` | any match's optimal tip |
| `ko_tips.py` | `KO-<round>` | any match's optimal tip |
| `tournament_bonusfragen.py` | `bonusfragen:scalar` | champion / SF set / Golden-Boot team / any group winner |
| `vectorized_mc.py` | `bonusfragen:vectorized` | same (separate scope — S11 engine divergence must not ping-pong) |

Semantics: the first run of a scope records a baseline silently; new keys
(a new matchday) are silent; only value changes on existing keys alert.
Scopes merge-update, so a partial KO re-run keeps untouched baselines.
State files are per-machine — the alerts that matter fire on the ops machine
where runs recur.

## Constraints

- The free API is for **personal use**, rate-limited server-side; the scanner
  hook dedups by leg set so a 60s daemon does not spam.
- Messages are truncated at 1400 chars (`notify.MAX_TEXT_LEN`).
- `api.callmebot.com` must be reachable: it is **blocked by the default
  egress allowlist of the Claude Code container** (like the odds hosts) —
  run notifying commands on the ops machine, or add the host to the
  environment's network allowlist.
- Failure mode: `send_whatsapp()` returns False and writes one stderr line;
  it never raises (`tests/test_notify.py` pins this contract).
