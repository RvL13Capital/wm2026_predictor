# F9 Validation: Ablation Study & Backtest Analysis

> ⚠️ **SUPERSEDED IN PART (2026-06-06).** The ablation diagnosis in Sections 1–3 (real WC2022
> data) stands. **Section 4's conclusion is withdrawn**: it kept the engine on the basis of a
> Monte-Carlo simulation driven by the model's *own* probabilities — a circular argument that
> cannot validate the model (this is exactly finding F9). The honest out-of-sample verdict is in
> [`F9_OUT_OF_SAMPLE.md`](F9_OUT_OF_SAMPLE.md): across 2014+2018+2022 (192 real matches) the
> optimized model ties the baseline exactly (291–291) on points, is statistically indistinguishable
> on calibration, and a non-penalty-xG check finds the core λ over-scales favorites while the
> context layer adds no bias-invariant signal — R4 is **not** met on real data.

**Auftrag:** Ermitteln, warum das optimierte Modell in der WM 2022 Backtest-Suite gegen die Baseline-Poisson-Engine verliert (104 vs 99 Kicktipp-Punkte).

**Ergebnis:** Das optimierte Modell ist *theoretisch besser kalibriert*, verliert aber im kleinen Sample-Size-Szenario von WM 2022 (N=64) Kicktipp-Punkte aufgrund deterministischer "Über-Bestrafungen" durch Kontext-Parameter (Reise, Jetlag) bei Upset-Matches.

## 1. Feature Ablation (Punkt-Deltas)

Wir haben die Features einzeln abgeschaltet (`--no-context`, `--no-nb`, `--no-phase`), um den EV-Drop zu isolieren.

*   **ALL FEATURES ON:** 99 Punkte
*   **NO PHASE (Keine KO-Formel):** 99 Punkte (Phase verändert die Tip-Entscheidung bei diesen spezifischen 64 Spielen nicht wesentlich genug, um die rundenbasierten Scores zu kippen).
*   **NO NEGATIVE BINOMIAL (Rückkehr zu Poisson):** 101 Punkte (+2)
*   **NO CONTEXT (Keine Reise/Wetter/Rest-Tage):** 102 Punkte (+3)
*   **BASELINE (Kein NB, Kein Kontext, Kein Phase):** 104 Punkte

## 2. Ursachenanalyse (Der "Context"-Drop)

Warum kostet Kontext Punkte? Wir haben die Match-by-Match Logs (`--details`) mit und ohne Kontext verglichen.

**Schlüssel-Spiel 1: Tunisia vs. Australia (Actual: 0:1)**
*   `Base Tip`: 0:1 (4 Punkte)
*   `Opt Tip`: 1:0 (0 Punkte) -> **-4 Punkte Verlust**
*   *Warum?* Australien flog für die WM 11.000 Meilen und kreuzte 11 Zeitzonen, während Tunesien nur 1.500 Meilen reiste. Der Travel/Jetlag-Penalty in `predictor.py` senkte Australiens Lambda stark ab. Die Basis-Elo präferierte Australien extrem knapp (Base-Lambda: 0.99 vs 1.00), der Travel-Penalty kippte den Favoriten auf Tunesien. Australien gewann das Spiel aber in der Realität trotzdem knapp.

**Schlüssel-Spiel 2: Argentina vs. France (Actual: 7:5 / ET: 3:3 / 90m: 2:2)**
*   `Base Tip`: 2:1 (2 Punkte)
*   `Opt Tip`: 0:1 (0 Punkte) -> **-2 Punkte Verlust**
*   *Warum?* Frankreich war im Modell leicht aufgewertet (Form/Fitness oder Jetlag-Recovery).

## 3. Ursachenanalyse (Der "Negative Binomial"-Drop)

Negative Binomialverteilungen (Overdispersion) streuen die Torschusswahrscheinlichkeiten weiter um den Erwartungswert als Poisson.
*   **Auswirkung auf Kicktipp:** Da Kicktipp "Exakte Ergebnisse" überproportional hoch bepunktet (4 vs 3 vs 2), ist eine schmalere Poisson-Verteilung oft "Kicktipp-EV-technisch" im Vorteil, weil sie zu klaren Tendenzen (z.B. 1:0) neigt. NB zieht Wahrscheinlichkeiten abseits vom 1:0 in Extrem-Szenarien (3:1, 0:0, 2:2), was den Erwartungswert des *exakten* Tipps senkt. Manchmal wählt die Engine dann sicherheitshalber konservativere Differenz-Tipps, die weniger Varianz haben.

## 4. Fazit & Handlungsentscheidung

**[WITHDRAWN — see banner at top.]** The original text argued the baseline "won by chance" on
WC2022 and that the extended model "remains mathematically superior over tens of thousands of games,
as proven in the Monte-Carlo simulation." That defense is circular: a MC simulation that samples
outcomes from the model's own probability grids measures self-consistency, not real-world accuracy.

**Honest replacement (2026-06-06).** Out-of-sample per-match Kicktipp backtests across 2014 + 2018 +
2022 (192 real matches, pre-tournament Elo, no lookahead) show the optimized model **ties the baseline
exactly, 291–291**; Dixon-Coles + Negative Binomial never change the EV-optimal tip, and on calibration
(Brier/RPS/log-loss) the difference is statistically indistinguishable from zero (paired bootstrap, all
95% CIs span 0). A lower-variance non-penalty-xG check (StatsBomb, 2018+2022) finds the core Elo→λ has
real margin skill (npxG-margin r≈+0.57) but **over-scales favorites**, while the context layer's
apparent gain is a bias artifact that vanishes on the bias-invariant margin. **R4 is not met on real
data.** Full analysis and recommendations: [`F9_OUT_OF_SAMPLE.md`](F9_OUT_OF_SAMPLE.md).
