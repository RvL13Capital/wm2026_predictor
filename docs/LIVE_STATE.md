# Live-State Operations Runbook (S18)

`live_state.json` forces real results into the simulators so every re-sim and
scan conditions on what has actually happened. Consumers:

```bash
python3 vectorized_mc.py --sims 100000 --seed 42 --live-state data/live_state.json
python3 edge_scanner.py --live-state data/live_state.json [--daemon]
```

## Schema

One JSON object. Values are always `[goals_a, goals_b]` (integers, 0–15).
Two key forms:

| Key form | Example | Semantics |
|---|---|---|
| `"Team A vs Team B"` | `"Mexico vs South Africa": [2, 0]` | Pairing-keyed. Orientation is auto-swapped if the simulator schedules the fixture the other way round. Names must be **canonical English** (the keys of `predictor.WORLD_CUP_2026_TEAMS`); German/alt spellings in `TEAM_NAME_MAPPING` are caught by the validator but NOT by the simulators. |
| `"M73"` … `"M104"` | `"M89": [2, 1]` | Match-id-keyed (KO bracket slots). Applied in **bracket orientation** to every simulated pairing occupying that slot. KO overrides must not be draws (the bracket needs a winner). For shootout games enter the shootout-inflated total (pool convention `shootout_total`, gate G1) — e.g. 1:1 + pens 4:2 → `[5, 3]`. |

Group-stage matches use the pairing form; KO matches may use either (the
match-id form wins if both match).

## Cadence (tournament operations, plan S20)

1. After each final whistle: add/update the entry in `data/live_state.json`.
2. **Validate immediately** — a typo'd key is a *silent no-op* inside the
   simulators (the match keeps being simulated as if unplayed):
   ```bash
   python3 scripts/validate_live_state.py data/live_state.json
   ```
   Exit 0 = safe to use; exit 1 = fix the listed errors first.
3. Re-sim / re-scan with the file (commands above). The daemon (`--daemon
   --live-state …`) re-reads the file every interval, so step 3 is automatic
   while it runs.
4. Commit the updated file with the day's ops commit so re-sims are
   reproducible.

## Failure modes the validator catches

- Unknown / misspelled team names (would never match — **error**).
- Non-canonical spellings that the *validator* can resolve but the simulators
  can't (**warning** with the exact rewrite).
- Match ids outside M73–M104, draw scores on KO slots, non-integer or
  out-of-range goals, malformed values (**errors**).

## Known semantics (by design)

- A pairing key only overrides fixtures where that exact pairing occurs in a
  simulation; in KO slots with many possible pairings, prefer the match-id key.
- `"M103"` (third-place match) is accepted by the validator but the current
  simulators do not model M103 (plan S15, optional) — entry is harmless.
