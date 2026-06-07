#!/usr/bin/env python3
"""
Predict the 2018 World Cup from PRE-tournament (point-in-time) Elo and check it against what
actually happened. 2018 is the old 32-team format (8 groups → Round of 16). No venue/style
data exists for 2018 in this repo (stadium_data + XG_STRENGTH are 2026-specific), so this is
the pure probability engine on June-2018 Elo — i.e. an honest pre-tournament forecast, no
lookahead. Group scores are most-likely results; standings derive from them; knockouts are
decisive (favourite by win-probability). Output: report/wm2018_bracket.html
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
import backtest_wm2018 as w14
from make_bracket_html import CSS, esc, modal, win_probs, match_html

ELO = w14.PRE_WM2018_ELO
GROUPS = w14.WM2018_GROUPS
MD = [(1, 0, 1), (1, 2, 3), (2, 0, 2), (2, 1, 3), (3, 0, 3), (3, 1, 2)]


def elo(t):
    return ELO.get(t, {}).get("elo", 1500)


def grid_of(a, b):
    return predictor.predict_single_match({"team_a": a, "team_b": b, "elo_a": elo(a), "elo_b": elo(b)})["grid"]


def predict_group(a, b):
    return modal(grid_of(a, b))


def predict_ko(a, b):
    grid = grid_of(a, b)
    pa, pb = win_probs(grid)
    win = a if pa >= pb else b
    conf = (pa if win == a else pb) / (pa + pb) if (pa + pb) > 0 else 0.5   # win-share of the tie
    best, ga, gb = -1.0, (1 if win == a else 0), (0 if win == a else 1)
    for ka, gr in grid.items():
        for kb, p in gr.items():
            x, y = int(ka), int(kb)
            if x != y and ((x > y) == (win == a)) and p > best:
                best, ga, gb = p, x, y
    return {"a": a, "b": b, "ga": ga, "gb": gb, "win": win, "conf": conf}


def group_games():
    games = {}
    for g, ts in GROUPS.items():
        gl = []
        for md, i, j in MD:
            grid = grid_of(ts[i], ts[j])
            x, y = modal(grid)
            pa, pb = win_probs(grid); pd = max(0.0, 1 - pa - pb)
            conf = pa if x > y else (pb if y > x else pd)   # P(predicted direction)
            gl.append((md, ts[i], ts[j], x, y, conf))
        games[g] = sorted(gl)
    return games


def standings(games):
    table = {}
    for g, gl in games.items():
        st = {t: {"pts": 0, "gf": 0, "ga": 0} for t in GROUPS[g]}
        for _, a, b, x, y, _c in gl:
            st[a]["gf"] += x; st[a]["ga"] += y; st[b]["gf"] += y; st[b]["ga"] += x
            if x > y: st[a]["pts"] += 3
            elif y > x: st[b]["pts"] += 3
            else: st[a]["pts"] += 1; st[b]["pts"] += 1
        ranked = sorted(GROUPS[g], key=lambda t: (st[t]["pts"], st[t]["gf"] - st[t]["ga"], st[t]["gf"], elo(t)), reverse=True)
        table[g] = [(t, st[t]["pts"], st[t]["gf"] - st[t]["ga"], st[t]["gf"]) for t in ranked]
    return table


def build_ko(table):
    def res(slot):
        return table[slot[2:]][0][0] if slot.startswith("W_") else table[slot[2:]][1][0]
    r = {}
    r16 = [predict_ko(res(A), res(B)) for A, B in w14.R16_BRACKET]; r["R16"] = r16
    w = [m["win"] for m in r16]
    qf = [predict_ko(w[i], w[j]) for i, j in w14.QF_BRACKET]; r["QF"] = qf
    wq = [m["win"] for m in qf]
    sf = [predict_ko(wq[i], wq[j]) for i, j in w14.SF_BRACKET]; r["SF"] = sf
    ws = [m["win"] for m in sf]
    r["FINAL"] = [predict_ko(ws[0], ws[1])]
    r["CHAMP"] = r["FINAL"][0]["win"]
    r["SF_TEAMS"] = set(wq)           # the four semifinalists = QF winners
    return r


def main():
    # data-recalibrated goal model (LOTO-tuned for end-result accuracy; brackets only — not config.json):
    # lower base + more favourite-stretch + NO draw-boosting Dixon-Coles (ρ=0) + slight overdispersion.
    predictor.CONSTANTS["elo_baseline_goals"] = 1.15
    predictor.CONSTANTS["elo_scale_factor"] = 1200
    _orig_psm = predictor.predict_single_match
    predictor.predict_single_match = lambda row, *a, **k: _orig_psm(
        {**row, "rho": 0.0, "alpha_a": 0.06, "alpha_b": 0.06}, *a, **k)
    games = group_games()
    table = standings(games)
    ko = build_ko(table)
    champ = ko["CHAMP"]

    pred_gw = {g: table[g][0][0] for g in table}
    gw_hits = sum(1 for g in pred_gw if pred_gw[g] == w14.ACTUAL_GROUP_WINNERS.get(g))
    sf_hits = len(ko["SF_TEAMS"] & w14.ACTUAL_SF_TEAMS)
    champ_ok = champ == w14.ACTUAL_CHAMPION

    P = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>"
         "<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>World Cup 2018 — Model Prediction vs Actual</title><style>{CSS}"
         ".cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}"
         ".cmp .big{font-size:22px;font-weight:900}.ok{color:#0f5132}.no{color:#b02a37}"
         ".grp .x{float:right;font-size:11px;font-weight:800}"
         "</style></head><body>"]
    res_txt = "✓ correct" if champ_ok else "✗ — actual winner was " + esc(w14.ACTUAL_CHAMPION)
    P.append("<header><div class='wrap'><h1>FIFA WORLD CUP 2018 — MODEL PREDICTION vs ACTUAL</h1>"
             "<div class='sub'>Pre-tournament (June 2018) Elo · most-likely scorelines · no lookahead · "
             "recalibrated goal scale · hindsight check against the real outcome</div>"
             f"<div class='champ-banner'><span class='crown'>👑</span><div><span>Predicted champion</span><br>"
             f"<b>{esc(champ)}</b></div><span>&nbsp;·&nbsp;{res_txt}</span></div></div></header>")
    P.append("<div class='wrap'>")

    # scorecard
    P.append("<h2>Prediction vs reality</h2><div class='panel cmp'>")
    P.append(f"<div class='card'><h3>Champion</h3><div class='big {'ok' if champ_ok else 'no'}'>{esc(champ)}</div>"
             f"<div class='dark'>Actual: <b>{esc(w14.ACTUAL_CHAMPION)}</b> (runner-up {esc(w14.ACTUAL_RUNNER_UP)})</div></div>")
    P.append(f"<div class='card'><h3>Group winners correct</h3><div class='big'>{gw_hits} / 8</div>"
             f"<div class='dark'>predicted top of each group vs actual</div></div>")
    P.append(f"<div class='card'><h3>Semifinalists correct</h3><div class='big'>{sf_hits} / 4</div>"
             f"<div class='dark'>predicted final four: {', '.join(sorted(ko['SF_TEAMS']))}<br>"
             f"actual: {', '.join(sorted(w14.ACTUAL_SF_TEAMS))}</div></div>")
    P.append("</div>")

    # groups (standings ✓/✗ vs actual winner + fixtures)
    P.append("<h2>Group stage — predicted standings &amp; results</h2><div class='groups'>")
    for g in sorted(table):
        rows = ""
        actual_w = w14.ACTUAL_GROUP_WINNERS.get(g)
        for pos, (team, pts, gd, gf) in enumerate(table[g], 1):
            cls, tag = "", ""
            if pos == 1:
                ok = team == actual_w
                mark = f"<span class='x {'ok' if ok else 'no'}'>{'✓' if ok else '✗'}</span>"
                cls, tag = "adv", f"<span class='tag w'>WIN</span>{mark}"
            elif pos == 2:
                cls, tag = "adv", "<span class='tag r'>R-UP</span>"
            rows += f"<tr class='{cls}'><td class='pos'>{pos}</td><td>{esc(team)}{tag}</td><td class='pts'>{pts}</td></tr>"
        fx, last = "", None
        for md, a, b, x, y, conf in games[g]:
            if md != last:
                fx += f"<div class='mdl'>Matchday {md}</div>"; last = md
            wa = "fw" if x > y else ("dr" if x == y else "")
            wb = "fw" if y > x else ("dr" if x == y else "")
            fx += (f"<div class='fx'><span class='ta {wa}'>{esc(a)}</span><span class='s'>{x}&ndash;{y}<i>{conf*100:.0f}%</i></span>"
                   f"<span class='tb {wb}'>{esc(b)}</span></div>")
        P.append(f"<div class='grp'><div class='gh'>Group {g}</div><table>{rows}</table>"
                 f"<div class='fixtures'>{fx}</div></div>")
    P.append("</div>")

    # bracket (R16 already in tree order)
    P.append("<h2>Knockout bracket (predicted)</h2><div class='bracket'>")
    P.append("<div class='round'><div class='rh'>Round of 16</div>" + "".join(match_html(m) for m in ko["R16"]) + "</div>")
    P.append("<div class='round'><div class='rh'>Quarter-finals</div>" + "".join(match_html(m) for m in ko["QF"]) + "</div>")
    P.append("<div class='round'><div class='rh'>Semi-finals</div>" + "".join(match_html(m) for m in ko["SF"]) + "</div>")
    P.append("<div class='round fin'><div class='rh'>Final</div>" + match_html(ko["FINAL"][0]) + "</div>")
    P.append("<div class='round champ-col'><div class='rh'>Champion</div>"
             f"<div class='champ-box'><div class='crown'>🏆</div><div class='lbl'>PREDICTED</div>"
             f"<div class='nm'>{esc(champ)}</div><div class='cfin'>wins final · {ko['FINAL'][0]['conf']*100:.0f}%</div></div></div>")
    P.append("</div>")

    P.append("<footer>Pre-tournament forecast from June-2018 Elo (no lookahead); 2018 has no venue/style "
             "data in this repo, so this is the pure probability engine on point-in-time ratings. The "
             "hindsight check shows how a chalk-by-rating forecast fares against a real, upset-heavy World Cup.</footer>")
    P.append("</div></body></html>")

    os.makedirs("report", exist_ok=True)
    with open("report/wm2018_bracket.html", "w", encoding="utf-8") as f:
        f.write("".join(P))
    print(f"predicted champion: {champ}  (actual: {w14.ACTUAL_CHAMPION}, {'HIT' if champ_ok else 'MISS'})")
    print(f"group winners correct: {gw_hits}/8 | semifinalists correct: {sf_hits}/4")
    print("predicted group winners:", pred_gw)
    print("✓ wrote report/wm2018_bracket.html")


if __name__ == "__main__":
    main()
