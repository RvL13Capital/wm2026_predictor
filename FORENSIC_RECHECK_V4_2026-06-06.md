# Forensischer Recheck — V4-Stand (Git: HEAD 44fd604)

**Datum:** 2026-06-06, ~16:15 UTC · **Auditor:** Principal Quant Dev / Forensic Auditor
**Hinweis:** Die Ordner-Synchronisierung hat die früheren Audit-Dokumente (`FORENSIC_AUDIT_2026-06-06.md`, `ANALYSIS_SWOT.md`, `WORK_ORDER_VALIDATION_FIXES.md`) überschrieben — Audit-Trail-Verlust; Reports künftig mit committen. Befund-IDs (W1–W10, F9/F10, B-Nummern) referenzieren das Original-Audit von heute 15:20 UTC.
**Methode:** Jede Behauptung — auch die des projekteigenen `validation/VALIDATION_REPORT.md` — wurde unabhängig gegen den Worktree re-verifiziert (ausführbare Reproduktion, keine Übernahmen).

Repo-Zustand: `.git` vorhanden (bd11cab 14:26 → e11fa97 14:37 → 966a22b 14:38 → **HEAD 44fd604 17:38** "V4 complete state before V5 fixes", Zeiten +0200) + **dirty Worktree** (u. a. `M tournament_bonusfragen.py`, `D solver.py`, 4 Test-Dateien, untracked `data/matchday1_tips_v5.txt`).

---

## 1. Statusmatrix (alles selbst verifiziert)

| Befund | Status | Beweis |
|---|---|---|
| **W1 Elfmeter-DP (State-Collapse)** | ✅ **GEFIXT** (in HEAD) | Komplett neue State-Machine: echter Mid-Round-Abbruch (B schießt nicht mehr, wenn entschieden), Sudden-Death trackt Both-Score/Both-Miss als getrennte Zustände. Quantitativ: TV-Abstand zu einer korrekten Real-Semantik-Referenz (2M Trials) = **0.0012** (reines MC-Rauschen; alte Version: 0.19 gegen diese Semantik), Mittelwert 8.019 vs. 8.020, Summe 1.0, keine Ties; asymmetrischer Fall (0.82/0.70) ebenso sauber. Degenerat p=0: nur noch ±1-Tiebreak-Konvention `(0,1)/(1,0)` statt 5–6 Phantomtoren. |
| **W2 RNG-Seed-Korrelation** | ✅ **BEHOBEN** | `tournament_sim.py` gelöscht (committed, −670 Zeilen). Nachfolger `matchday_tips.py:133`: `match_seed = seed + match_index` → unabhängige Streams pro Spiel. |
| **W7 Globale Elo-Mutation** | ✅ gefixt / 🟡 neu eingeschleppt | `run_monte_carlo` ist jetzt Wrapper mit `try/finally` + `deepcopy`-Restore (✓). **Aber:** `matchday_tips.py:94–108` mutiert die globale Elo-Tabelle erneut ohne try/finally. |
| **W10 Markt-Namensbug** | 🟡 **⅔ gefixt** | Snapshot-Keys werden via `TEAM_NAME_MAPPING` normalisiert (tournament_bonusfragen.py:1624–1629): `Turkiye` ✓, `Bosnia-Herzegovina` ✓ — **`Congo DR` fehlt im Mapping** (nur "dr kongo"/"kongo dr") → DR-Congo-Markt wird weiterhin stillschweigend verworfen (verifiziert: nach Normalisierung fehlt genau `['DR Congo']`). |
| **W4 Markt-Heuristik (Unterkonfidenz)** | 🟡 **GEFIXT — ABER UNCOMMITTED** | Fix liegt nur im Worktree (`git diff`), nicht in HEAD: 0.73-Deckel entfernt, Draw = `0.27·(1−mismatch)`. End-to-End Spanien–Katar: 1x2 **89.0 / 4.0 / 7.0 %** (vorher 67.6/27.0/5.4), λ = 4.47, Tipp **4:0** statt 2:0 → Favoriten-Kompression beseitigt. `sqrt`-Share bleibt eine theoretisch unbegründete, unvalidierte Heuristik. |
| **W5 Dampening-No-Op** | 🟡 **GEFIXT — ABER UNCOMMITTED** | Neu: Underdog wird Richtung eigener `attack_str` gezogen (Z. 388/391). Frankreich–Haiti: form_b 0.656 ≠ raw 0.650 → Formel wirkt jetzt tatsächlich. |
| **W3 Split-Brain** | 🟡 **TEILWEISE** | ✓ Matchday-Tipps nutzen jetzt den vollen Stack (Injury-Elo, Squad-Value, xG-Form, Höhe/Akklimatisierung, Schedule-Kontext; B3 bestätigt gefixt). Restbestand: (a) Bonusfragen-KO-Sim nutzt weiter den **Coinflip-Elfer** clamp [0.40, 0.60] (Z. 1027–1030) statt der frisch reparierten DP + `PENALTY_STRENGTH`; (b) `run_matchday(..., market_probs)` — Parameter wird **nie benutzt**, kein `--odds-snapshot`-CLI → Matchday-λ ohne Markt, Bonusfragen-λ mit Markt (Gewicht 0.7) für dieselbe Partie. |
| **W6 Solver-Duplikat** | 🟡 | `solver.py` gelöscht — aber **uncommitted** (`git status: D solver.py`), zugehörige Test-Edits ebenfalls uncommitted → Baum inkonsistent. |
| **W8 Silent Degradation** | ❌ OFFEN | `except (ValueError, TypeError): pass` beim Odds-Parse (predictor.py:1665) unverändert; der DR-Congo-Drop (W10) ist derselbe Fehlermodus. |
| **B5 Datenlücken** | ✅ (Worktree) | xG für Egypt/NZ/Scotland/Sweden ergänzt (uncommitted); `SQUAD_MARKET_VALUES` inkl. Uruguay vollständig — beide Lücken-Checks leer. |
| **F10 Provenienz / Phantom-Code** | 🟡 **GROSSER FORTSCHRITT, EINE LÜCKE** | ✓ Git, ✓ code-generierter Header (Timestamp/Seed/Cmd/Commit) in beiden Writern, ✓ `tests/gate_check.py` (besteht auf dem v4-Paar), ✓ Dateiname = Simzahl (100k_v4 = `--sims 100000`). **Lücke — Dirty-Tree-Workflow läuft weiter:** v4-Outputs zitieren `Commit: 966a22b`, obwohl der erzeugende Code dort nicht committed war (matchday_tips.py existiert erst in 44fd604); Regeneration am HEAD weicht in λ-Nachkommastellen ab (0.544→0.553; Drift = das spätere W5-Fix); `matchday1_tips_v5.txt` ist bereits wieder ein untracked Output aus dem aktuell dirty Worktree. Header braucht ein Dirty-Flag (`git describe --dirty`). |
| **F9 Backtest WC2022** | ❌ **WEITER NEGATIV** | Re-Run am HEAD: **Baseline 104 vs. Optimiert 99** (Δ −5, −0.078/Spiel). Ablation jetzt committed (`--no-context` +3, `--no-nb` +2, `--no-phase` ±0) — saubere Diagnose, aber die dokumentierte Entscheidung „Engine bleibt" (`validation/backtest_engine_real.md`) stützt sich auf eine **zirkuläre Begründung**: eine MC-Simulation mit den modelleigenen Wahrscheinlichkeiten kann das Modell nicht validieren. Keine per-Match-Folds 2018/2014 nachgereicht. Abnahmekriterium R4 bleibt verfehlt. |

## 2. Neue Befunde im V4/V5-Code

- **N1 🔴 Host-Bonus geht verloren:** `matchday_tips.py:59/68` setzt `status = "host"`; `predictor.normalize_status("host")` → **"Neutral"** (verifiziert). Der Host-Effekt (att +0.08 / def −0.06) fehlt damit in **allen** Matchday-Tipps der Gastgeber; nur der Fan-Anteil wirkt — und der wird als `"90"` übergeben und vom Clamp zu 1.0 statt 0.90 interpretiert (Bonusfragen nutzen korrekt 0.70/0.30). Mexiko-λ dadurch ≈ 15 % zu niedrig.
- **N2 🟠 Toter Parameter `market_probs`** in `run_matchday()` (s. W3b) — Deliverables divergieren systematisch.
- **N3 🟡 Testsuite im Dirty-State rot:** committed Baseline `validation/baseline_tests.txt` = 153/153 ✓; aktueller Worktree in meiner Sandbox **136 Pass / 17 Errors** (davon ≥5 Sandbox-`PermissionError` auf temp-CSVs — Umgebungsartefakt; der Rest hängt an den uncommitted Test-Edits + `solver.py`-Löschung). Zustand nicht zertifizierbar, bis Deletions + Test-Anpassungen committed sind.
- **N4 🟡 `__pycache__`-Binärdateien im Git-Index** (jede Diff voller .pyc-Rauschen) — `.gitignore` fehlt.

## 3. Verdikt

**Echter, substanzieller Fortschritt.** Die zwei härtesten Mathe-Defekte sind erledigt: die Elfmeter-DP ist jetzt nachweislich korrekt (TV 0.001 gegen unabhängige Referenz, inkl. Real-Semantik-Upgrade), die RNG-Korrelation ist mitsamt `tournament_sim.py` eliminiert. Provenienz-Infrastruktur (Git, Header, Gate-Check) steht, Datenlücken sind zu, die Markt-Kalibrierung ist im Worktree repariert (Spanien–Katar 4:0 statt 2:0).

**Was den Gold-Standard weiter blockiert, in Reihenfolge:**
1. **Committen.** Die wertvollsten Kalibrierungs-Fixes (W4/W5), die xG-Ergänzungen und die `solver.py`-Bereinigung liegen uncommitted — und es entstehen schon wieder Outputs aus diesem Zustand (v5). Genau dieser Workflow hat die Phantom-Historie erzeugt. Dazu: Dirty-Flag in den Provenienz-Header, `.gitignore` für `__pycache__`.
2. **N1 fixen** (`"host"` → `"True Home"`, fan_pct als 0.90/0.10) — ein Zweizeiler mit messbarem λ-Effekt auf alle Gastgeber-Spiele.
3. **`Congo DR`** ins `TEAM_NAME_MAPPING`; Odds-Fallbacks laut loggen statt `pass` (W8).
4. **KO-Elfer der Bonusfragen-Sim** auf die reparierte `penalty_shootout_distribution` + `PENALTY_STRENGTH` umstellen (letzter großer Split-Brain-Rest).
5. **F9 ehrlich schließen:** per-Match-Kicktipp-Backtests 2018 + 2014 als zusätzliche Out-of-Sample-Folds; erst wenn das Modell aggregiert über ≥3 Turniere die Baseline schlägt, ist die Mehrkomplexität gerechtfertigt. Die aktuelle „MC beweist Überlegenheit"-Argumentation ist zirkulär und als Validierung unzulässig.
