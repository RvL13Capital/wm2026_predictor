# Scoring-environment prior: CWC 2025 + WC 2014–22 vs the engine's group-stage claims

*Registered 2026-06-11 (opener day, before any 2026 result). Companion evidence to the
λ-freeze checkpoint amendment in `points_recalibration.md`.*

## Why this exists

The 2025 FIFA Club World Cup was the dress rehearsal for WC 2026: same US stadiums,
same summer heat, an expanded field with comparable mismatch structure. Its group
stage was reported as "high-scoring". Before trusting the engine's clean-sheet-heavy
group-stage claims (70 of 72 EV tips blank one team), we measured what the CWC —
and the engine's own 144-match WC validation set — actually say.

## Data

- CWC 2025 group stage: all 48 results, fixturedownload.com CSV (fetched 2026-06-11).
- Real WC group stages 2014/2018/2022: the repo's own `data/wc{2014,2018,2022}_results.csv`
  (144 GROUP matches — the λ calibration's validation set).
- Engine: per-match grids for all 72 WC2026 group fixtures, deterministic Elo+stack
  path (`matchday_tips.run_matchday(md, 0, 42, None, None)`), production calibration.

## The table

| Statistic                                  | Engine claim (2026, n=72) | CWC 2025 raw (n=48) | CWC 2025 minnows stripped (n=37) | Real WC group 14–22 (n=144) |
|--------------------------------------------|------------------|--------|--------|--------|
| Goals / match                              | **2.09**         | 3.00   | 2.54   | 2.62   |
| Draw share                                 | 26%              | 27%    | 32%    | 19%    |
| Both teams score (BTTS)                    | **26%**          | 44%    | 43%    | **48%** |
| Clean-sheet games                          | **74%**          | 56%    | 57%    | **52%** |
| Win-by-1 games: both-scored share          | **26%**          | 54%    | 45%    | **54%** |

(“Minnows stripped” removes the 11 games involving Auckland City, Al Ain, Wydad,
Urawa — the CWC's raw 3.00 was mismatch-driven; the core rate matches WC norms.)

## Findings

1. **US-2025 conditions did not inflate scoring for comparable matchups.** CWC core
   rate 2.54 ≈ WC group norms (2.62 over 2014–22). The headline 3.00 came from
   blowouts; WC 2026's 48-team field will have more of those than a 32-team WC, and
   the engine already tips them big (5:0s). Heat did not visibly suppress scoring.
2. **The engine's totals run ~0.5 goals/match low** (2.09 claimed vs ~2.5–2.6 real).
   Known and accepted: the low-λ calibration is points-validated (299/192,
   `points_recalibration.md`), not probability-calibrated.
3. **The clean-sheet overconfidence is real and large.** In real WC group play, half
   the one-goal games have the loser scoring (54%; CWC agrees) — the engine claims
   26%. Same for BTTS: claimed 26% vs real 48%. The "always one team at 0" tip shape
   rests on exact-cell claims that history contradicts.
4. **Points impact stays ≈ neutral** — 1:0 and 2:1 share a Tordifferenz band, so with
   the real band composition near 50/50 the exact-pick choice is close to a coin-flip
   tiebreak; this is consistent with the λ grid finding that retuning gains ≈ 0 points.
   The 299/192 measurement stands.
5. **Betting layer warning (actionable):** grids claiming 26% BTTS / 2.09 totals
   against a ~48% / ~2.6 world will generate systematic phantom "edges" on Unders,
   No-BTTS and x:0 exact-score derivative books, and overstate draw probabilities in
   near-even games (engine 26% draws vs 19% real group rate — the 32 draw legs the
   scanner flagged on opener day are exactly this artifact). Paper-mode ledger entries
   in these market classes should be read as calibration probes, not edge. Gate G2
   remains the only path to real money.
6. **Checkpoint power:** if 2026 resembles 2014–22 on the band composition, the
   pre-registered tripwire (`scripts/lambda_checkpoint.py`) has substantial power and
   a real chance of firing on Jun 27 — which is precisely the sanctioned route to a
   BTTS-aware recalibration before the KO rounds.

## Caveats

- Club ≠ national teams (cohesion, attacking quality); the CWC transfer is a prior,
  not proof — but the 144 real WC matches carry the same message with more weight.
- n=48 (CWC) and n=65 (win-by-1 subset of WC 14–22) keep confidence intervals wide;
  none of this overturns the points validation, it bounds what the grids' cells mean.
- Engine aggregates reproduced market-blind; lock-night blends shift 1X2 splits but
  barely move the BTTS/exact cell structure that drives the gap.

## Addendum (same day) — λ-family saturation & the two-track decision

Double-checked whether the calibrated λ (bg=1.25 — the log-loss LOTO pick on
all three held-out folds, `validation/recalibration.txt`) closes the gaps.
Result over the 72 fixture grids:

| Config            | E[goals] | draw% | BTTS% | 1g-both% |
|-------------------|---------:|------:|------:|---------:|
| REALITY (WC 14–22)|     2.62 |    19 |    48 |       54 |
| production bg=1.0 |     2.09 |    26 |    26 |       26 |
| bg=1.25 sf=1600   |     2.61 |    21 |  34   |     37   |
| bg=1.25 sf=1200   |     2.90 |    19 |    32 |       36 |
| bg=1.25 sf=2000   |     2.47 |    23 |    35 |       37 |
| bg=1.15 sf=1200   |     2.67 |    20 |    29 |       32 |

bg=1.25 reproduces totals and draw rate almost exactly, but **BTTS saturates
at ~32–36% across the whole plausible λ family vs 48% real** — independent
biPoisson + DC-corner has no score-state dependence (trailing teams pushing,
2-0 becoming 2-1) and no λ can synthesize it. Structural, not a tuning miss.

**Decision (shipped 2026-06-11, pre-KO-freeze):** two-track calibration.
`edge_scanner.SCANNER_PRICING_CALIBRATION` (bg=1.25/sf=1600) applies ONLY to
match-market pricing (`model_match_1x2`, via the `_calibrated_pricing` context
manager); the tips path and the tournament matrix keep frozen production
constants (points floor re-verified: 299/192). BTTS / exact-score books are
refused outright (`_STRUCTURALLY_UNPRICEABLE`). Ledger meta now records
`pricing_calibration` so pre/post regimes stay separable in the paper record.

Consequence for the Jun-27 λ checkpoint: if the tripwire fires, the realistic
action is scoping down exact-cell claims (and this two-track split), NOT a
points-λ retune — the measured grid already shows no family member both beats
the 295 floor and fixes the cells.
