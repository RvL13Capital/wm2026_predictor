# Squad-value age bias — mechanism confirmed, impact bounded (measured)

*Registered 2026-06-11. Question raised: Transfermarkt-style market values are
inflated for young players (resale value, not current skill) — does the
value→skill mapping distort the model, worst case completely?*

## Where squad value enters (two stacked pathways)

1. **Global Elo overlay** (`tournament_bonusfragen.compute_squad_elo_adjustments`,
   shared by the sims and the scanner): `±40` from log10(value/median≈204M),
   **plus `±20` from `change_pct × 2`** — the Dec-2025→Jun-2026 Transfermarkt move,
   interpreted as "form".
2. **Per-match λ context term** (`predictor.get_adjusted_lambdas`):
   `0.15·ln(XI ratio) + 0.05·ln(bench ratio)` on the λ exponents — with the fixed
   65/35 split this is `0.20·ln(value ratio)`, i.e. the SAME value-level signal
   again (S23 collinearity note). Uses level only; `change_pct` is overlay-only.

## The age artifact is real — decomposition of the overlay

Young players appreciate with age; veterans depreciate mechanically at constant
skill. `change_pct` therefore conflates age-curve with form. Measured June-2026
adjustments (form share = |form| / (|value|+|form|)):

| Team        | value | chg%  | value-Elo | form-Elo | total | form share |
|-------------|------:|------:|----------:|---------:|------:|-----------:|
| Ivory Coast |  522  | +12.0 |     +16.3 |  +20.0(cap) | +36 | 55% |
| Ecuador     |  376  | +10.0 |     +10.6 |    +20.0(cap) | +31 | **65%** |
| Turkey      |  474  |  +7.0 |     +14.6 |    +14.0 | +29 | 49% |
| Japan       |  281  |  +5.5 |      +5.6 |    +11.0 | +17 | 66% |
| Canada      |  204  |  +7.0 |       0.0 |    +14.0 | +14 | **100%** |
| Croatia     |  388  |  −6.0 |     +11.2 |    −12.0 |  −1 | 52% |

Croatia is the symmetric victim: its genuine +11 value-Elo is fully erased by the
aging-depreciation "form" penalty.

## But the worst case does NOT materialize — ablation (20k sims, seed 42, Elo-only)

`--sims 20000 --seed 42` with vs without the overlay (`--no-squad-value`):

| Team      | Champion WITH | Champion W/O | relative |
|-----------|--------------:|-------------:|---------:|
| Spain     | 22.1% | 20.1% | +10% |
| Germany   |  6.5% |  6.0% |  +8% |
| Ecuador   |  2.9% |  2.6% | +10% |
| Turkey    |  2.0% |  2.0% |   ~0 |
| Brazil    |  3.7% |  4.2% | −13% |
| Croatia   |  1.7% |  2.1% | **−21%** |

**Zero group-winner flips** (12/12 identical tips, probabilities move ≤3pp).
The ±60 cap keeps the term an order of magnitude too small to "mess up the
complete score-to-skill value". Consistent with F9: the context stack is
points-neutral over 192 matches.

**Important negative finding:** the Ecuador/Turkey outright gaps vs the market
(model 2.8%/2.9% vs de-vigged 0.8%/1.2% on opener day) are NOT primarily caused
by this term — Ecuador keeps 2.6% champion / 16.2% SF even with the overlay off.
Their optimism lives in the base (post-friendlies) Elo and tournament dynamics.
The scanner's young-team outright "edges" remain suspect, but for a different
reason than the value bias.

## Disposition

- **No engine change now** (pre-registered record stands; F9 points-neutrality;
  Jun-28 freeze approaching; effect bounded).
- **S23 scope extended** (post-tournament): when real per-player data replaces
  the 65/35 split, (a) age-normalize market values (divide out the age curve)
  before the value→Elo/λ mapping, and (b) replace `change_pct` with a
  results-based form signal — value *change* is the most age-contaminated input
  in the stack (Canada's entire +14 is the form term).
- Scanner interpretation note: treat young-squad outright edges as unexplained
  model-vs-market divergence pending the post-tournament Elo audit, not as value.

## Addendum (same day) — age is a conditioning variable, not (only) a value discount

Pushback accepted on the "Croatia victim" framing: at the Modrić-generation
extreme, depreciation does track real skill decline. The sharper point is that
for old squads the binding constraint is **recovery between matches**, which a
static Elo discount cannot represent — the cost should *compound through the
tournament* (up to 8 matches, summer heat, ET carry-over).

**What the engine does today (measured, age-blind):**

- Vectorized ET fatigue: penalty `0.10 / min(2.0, bench_value/50)` for ONE
  following round, binary. Bench ≥ €100M caps the resilience at 2.0, so every
  realistic KO contender takes the identical minimum 5% — Croatia (oldest core)
  and Ecuador (youngest) are treated the same. Differentiation only punishes
  poor-bench minnows. No cumulative load, no rest days, no age input anywhere.
- Scalar engine: no fatigue at all (momentum-Elo instead; S11 divergence).
- Net effect: the age penalty lands statically in the GROUP stage (where
  conditioning barely binds) via `change_pct`, while the KO rounds (where it
  binds hardest) apply none. Backwards on both ends.

**In-tournament lever (allowed, no engine change):** `ko_tips.py --fatigued`
is a manual flag. Ops rule for the KO rounds: age-weight the call — an
old-core team coming off ET (or a 3-day turnaround) gets flagged by default;
a young squad with full rest is a judgment call. This is operator input to an
existing validated lever, not a model change.

**S23 design note (post-tournament):** replace binary ET fatigue with a
cumulative-load state (matches played, ET count, rest days, travel) modulated
by XI-age — `penalty × age_factor(avg XI age)` — and key resilience to squad
AGE structure, not bench price (bench value is itself age-inflated, and the
2.0 cap makes it non-functional among contenders anyway). Data requirement:
XI-weighted average age per squad. Honest caveat: the historical validation
subset (KO matches following ET, 2014–22) is ~20 games — the term may have to
ship as theory-priced with wide uncertainty rather than backtest-validated.
