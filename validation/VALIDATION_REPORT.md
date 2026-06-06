# VALIDATION REPORT (Phase 1)
*Erstellt: 2026-06-06*

**Kanonisches Verzeichnis:** `~/.gemini/antigravity/scratch/wm2026_predictor`
*Hinweis:* Der aktuellste Code lag bereits hier und beinhaltete teilweise schon Fixes aus meiner letzten "V3"-Iteration (die sich mit der Ausarbeitung dieses Work-Orders überschnitten haben). Ich werte die Behauptungen B1–B10 daher präzise basierend auf der Codebase und markiere, falls ein Bug in V3 bereits antizipiert und eliminiert wurde.

| ID | Urteil | Begründung / Beweis |
|---|---|---|
| **B1** | **BESTÄTIGT** | `python3 -c "import predictor; d=predictor.penalty_shootout_distribution(0.0,0.0,0.0,0.0); print(sorted(d.items()))"` ergibt `[((5, 6), 0.5), ((6, 5), 0.5)]`. Bei p=0 führt die Schleife zu unmöglichen Scores ohne Abbruch. |
| **B2** | **BESTÄTIGT** | `python3 backtest.py --csv data/wc2022_full.csv` liefert: `Baseline Total Points: 104.0`, `Optimized Total Points: 99.0` (Δ = -5.0). Die optimierte Engine unterliegt auf dem vollen Set. |
| **B3** | **WIDERLEGT** | *Bereits in V3 von mir behoben.* Im aktuellen kanonischen Code nutzt `tournament_sim.py` bereits den vollen Stack (`INJURY_ELO_ADJUSTMENTS`, Squad Values, xG-Multiplikatoren, `ALTITUDE_ACCLIMATIZATION`). Output: Mexiko `λ_adj` steigt korrekt auf `1.375`. |
| **B4** | **WIDERLEGT** | *Bereits in V3 von mir behoben.* Die `TEAM_NAME_MAPPING`-Normalisierung wurde bereits in die JSON-Parser-Logik von Polymarket integriert; `tournament_bonusfragen.py` erfasst die Namen sauber. |
| **B5** | **TEILWEISE BESTÄTIGT** | Die fehlenden xG-Daten für Scotland, Sweden, Egypt und New Zealand wurden von mir in V3 bereits gepatcht (`xG fehlt: []`). Jedoch **fehlt Uruguay** tatsächlich noch in den `SQUAD_MARKET_VALUES`. |
| **B6** | **BESTÄTIGT** | Code-Inspektion `tournament_sim.py`: `rng_seed=rng_seed` wird in Zeile 564 starr durchgeschleift, was zu korrelierten Random-Streams über alle Spiele führt. |
| **B7** | **BESTÄTIGT** | Die Wahrscheinlichkeiten klaffen auseinander. Hauptursache: `matchday1.csv` ist handgepflegt und weist komplett falsche Paarungen auf (z.B. Brazil vs. Morocco in der Gruppe), wodurch die Einzelspiel-Engine mit asymmetrischen Context-Daten operiert. |
| **B8** | **BESTÄTIGT** | Die Tip-Engine glättet die Favoriten viel zu stark. Die Wahrscheinlichkeiten (z.B. Brasilien vs Marokko nur 38%) spiegeln den Elo-Unterschied nicht adäquat wider. |
| **B9** | **WIDERLEGT** | *Bereits in V3 von mir behoben.* `bonusfragen_100k_v3.txt` trägt bereits den korrekten Header mit Cmd und Seed. |
| **B10**| **BESTÄTIGT** | Der Header der 100k-Datei gibt fälschlicherweise "Basierend auf 10,000 Monte-Carlo-Simulationen" an (Hardcoded-String in der Writer-Methode). |

---
**Fazit Phase 1:** Die unabhängige Validierung ist abgeschlossen. Keine Code-Änderungen vorgenommen. Phase 2 (Fixes für die bestätigten Befunde) kann nun gemäß Implementation Plan starten.
