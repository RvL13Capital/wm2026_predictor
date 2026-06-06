#!/usr/bin/env python3
"""
Render a professional WC2026 bracket (HTML) from the model's predictions:
- Group standings (12 groups) with predicted top-2 + best-third qualifiers.
- The full 48-team knockout tree R32 → Final with predicted scorelines and winners.
- A bonusfragen panel (champion, top-scorer team, semifinalists) with favorite + dark horse.

Bracket is the deterministic "favourite advances" path (higher model strength wins, score =
the model's optimal tip), wired through the real 2026 bracket (GROUPS / THIRD_PLACE_POOLS /
R32_BRACKET / R16_BRACKET / QF_BRACKET / SF_BRACKET from tournament_bonusfragen). Group winners
equal the MC sim's modal winners and the champion equals the MC favourite, so the tree is
consistent with the probabilities shown. Bonusfragen %s are from this session's 20k MC run.
Output: report/wm2026_bracket.html
"""
import os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
import tournament_bonusfragen as tbf

ELO = predictor.WORLD_CUP_2026_TEAMS

# Bonusfragen probabilities from this session's 20,000-sim run (run_monte_carlo, seed 42)
BF = {
    "champion": [("Spain", 22.6), ("Argentina", 16.0), ("France", 12.7), ("England", 8.0),
                 ("Portugal", 6.0), ("Germany", 5.0), ("Ecuador", 3.0)],
    "champion_dark": ("France", 12.7),
    "scorer": ("France", 29.0), "scorer_dark": ("Norway", 11.0),
    "sf": [("Spain", 47), ("France", 40), ("Argentina", 37), ("England", 26)],
    "sf_dark": ("Germany", 24),
}


def elo(t):
    return ELO.get(t, {}).get("elo", 1500)


# ---- Group standings (rank each group by model strength = Elo) ----
def group_standings():
    return {g: sorted(teams, key=elo, reverse=True) for g, teams in tbf.GROUPS.items()}


def best_eight_thirds(stand):
    thirds = {g: stand[g][2] for g in stand}                      # 3rd place in each group
    ranked = sorted(thirds.items(), key=lambda kv: elo(kv[1]), reverse=True)
    qualified = {g for g, _ in ranked[:8]}
    return thirds, qualified


def assign_thirds(thirds, qualified):
    """Backtracking slot solver — mirrors tournament_bonusfragen._solve_third_assignment."""
    slot_order = ["M75", "M77", "M79", "M80", "M81", "M82", "M85", "M88"]

    def solve(idx, used, asn):
        if idx == len(slot_order):
            return dict(asn)
        slot = slot_order[idx]
        for g in tbf.THIRD_PLACE_POOLS[slot]:
            if g in qualified and g not in used:
                asn[f"3_{slot}"] = thirds[g]; used.add(g)
                r = solve(idx + 1, used, asn)
                if r is not None:
                    return r
                used.discard(g); del asn[f"3_{slot}"]
        return None
    return solve(0, set(), {}) or {}


# ---- Match prediction (regular-time scoreline; favourite advances, ties broken by Elo) ----
def predict(a, b):
    res = predictor.predict_single_match({"team_a": a, "team_b": b, "phase": "GROUP"})
    ga, gb = (int(x) for x in res["optimal_tip"].split(":"))
    if ga > gb:
        win, et = a, False
    elif gb > ga:
        win, et = b, False
    else:
        win, et = (a if elo(a) >= elo(b) else b), True   # KO must resolve → favourite a.e.t.
    return {"a": a, "b": b, "ga": ga, "gb": gb, "win": win, "et": et}


def build_ko(stand, thirds_assigned):
    def resolve(slot):
        if slot.startswith("W_"): return stand[slot[2:]][0]
        if slot.startswith("R_"): return stand[slot[2:]][1]
        return thirds_assigned.get(slot, "TBD")

    rounds = {}
    r32 = [predict(resolve(a), resolve(b)) for a, b in tbf.R32_BRACKET]
    rounds["R32"] = r32
    w32 = [m["win"] for m in r32]
    r16 = [predict(w32[i], w32[j]) for i, j in tbf.R16_BRACKET]
    rounds["R16"] = r16
    w16 = [m["win"] for m in r16]
    qf = [predict(w16[i], w16[j]) for i, j in tbf.QF_BRACKET]
    rounds["QF"] = qf
    wqf = [m["win"] for m in qf]
    sf = [predict(wqf[i], wqf[j]) for i, j in tbf.SF_BRACKET]
    rounds["SF"] = sf
    wsf = [m["win"] for m in sf]
    final = predict(wsf[0], wsf[1])
    rounds["FINAL"] = [final]
    rounds["CHAMP"] = final["win"]
    return rounds


# ---- display order so the tree nests correctly ----
def display_orders():
    qf_o = [i for pair in tbf.SF_BRACKET for i in pair]          # [0,1,2,3]
    r16_o = [i for q in qf_o for i in tbf.QF_BRACKET[q]]         # 8
    r32_o = [i for r in r16_o for i in tbf.R16_BRACKET[r]]       # 16
    return r32_o, r16_o, qf_o


# ============================== HTML ==============================
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
 background:#0d1b2a;color:#1b263b;padding:0 0 60px}
.wrap{max-width:1480px;margin:0 auto;padding:0 24px}
header{background:linear-gradient(120deg,#0d1b2a,#1b3a5b 60%,#16635a);color:#fff;padding:34px 0 30px;
 border-bottom:4px solid #f4c430;margin-bottom:28px}
header h1{font-size:30px;letter-spacing:.5px;font-weight:800}
header .sub{opacity:.8;margin-top:6px;font-size:14px}
.champ-banner{margin-top:20px;display:inline-flex;align-items:center;gap:14px;background:rgba(244,196,48,.14);
 border:1px solid #f4c430;border-radius:12px;padding:12px 22px}
.champ-banner .crown{font-size:30px}
.champ-banner b{font-size:24px;color:#f4c430;letter-spacing:.5px}
.champ-banner span{opacity:.85;font-size:13px}
h2{color:#fff;font-size:17px;margin:30px 0 14px;border-left:4px solid #f4c430;padding-left:10px;letter-spacing:.4px}
.panel{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.card{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
.card h3{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#5a6b80;margin-bottom:10px}
.row{display:flex;justify-content:space-between;align-items:center;padding:3px 0;font-size:14px}
.row .p{color:#16635a;font-weight:700;font-variant-numeric:tabular-nums}
.fav{font-weight:800}
.dark{margin-top:8px;padding-top:8px;border-top:1px dashed #d4dae3;font-size:13px;color:#9c5a00}
.dark b{color:#9c5a00}
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(216px,1fr));gap:12px}
.grp{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 3px 10px rgba(0,0,0,.2)}
.grp .gh{background:#1b3a5b;color:#fff;font-weight:700;padding:7px 12px;font-size:13px;letter-spacing:.5px}
.grp table{width:100%;border-collapse:collapse;font-size:13px}
.grp td{padding:6px 12px;border-top:1px solid #eef1f5}
.grp td.pos{color:#9aa7b8;width:18px}
.grp tr.adv td{background:#eafaf1;font-weight:700;color:#0f5132}
.grp tr.third td{background:#fff8e6}
.grp .tag{float:right;font-size:10px;font-weight:700;padding:1px 6px;border-radius:8px}
.grp .tag.w{background:#0f5132;color:#fff}.grp .tag.r{background:#198754;color:#fff}.grp .tag.q{background:#f4c430;color:#3a2c00}
/* bracket */
.bracket{display:flex;gap:18px;align-items:stretch;background:#fff;border-radius:12px;padding:20px 16px;
 box-shadow:0 4px 14px rgba(0,0,0,.25);overflow-x:auto}
.round{display:flex;flex-direction:column;justify-content:space-around;min-width:172px;flex:1}
.round .rh{position:sticky;top:0;text-align:center;font-size:11px;font-weight:800;letter-spacing:1px;
 color:#5a6b80;text-transform:uppercase;margin-bottom:8px}
.m{background:#f7f9fc;border:1px solid #e2e8f0;border-radius:7px;margin:5px 0;overflow:hidden;font-size:12.5px}
.m .t{display:flex;justify-content:space-between;padding:5px 9px}
.m .t.win{background:#eafaf1;font-weight:800;color:#0f5132}
.m .t.lose{color:#8a97a8}
.m .t .sc{font-variant-numeric:tabular-nums;font-weight:700}
.m .et{font-size:9px;color:#9c5a00;text-align:right;padding:0 9px 3px}
.fin .m{border:2px solid #f4c430;background:#fffdf5}
.champ-col{justify-content:center;align-items:center;min-width:150px}
.champ-box{background:linear-gradient(135deg,#f4c430,#e0a800);color:#3a2c00;border-radius:12px;padding:18px 14px;
 text-align:center;box-shadow:0 6px 18px rgba(224,168,0,.5)}
.champ-box .crown{font-size:26px}.champ-box .lbl{font-size:10px;letter-spacing:1.5px;font-weight:700;opacity:.7}
.champ-box .nm{font-size:20px;font-weight:900;margin-top:2px}
footer{color:#8aa0b8;font-size:12px;margin-top:26px;line-height:1.5}
"""


def esc(s):
    return html.escape(str(s))


def match_html(m, extra=""):
    def row(team, sc, is_win):
        cls = "win" if is_win else "lose"
        return f'<div class="t {cls}"><span>{esc(team)}</span><span class="sc">{sc}</span></div>'
    et = '<div class="et">a.e.t.</div>' if m.get("et") else ""
    return (f'<div class="m {extra}">{row(m["a"], m["ga"], m["win"]==m["a"])}'
            f'{row(m["b"], m["gb"], m["win"]==m["b"])}{et}</div>')


def main():
    stand = group_standings()
    thirds, qualified = best_eight_thirds(stand)
    assigned = assign_thirds(thirds, qualified)
    ko = build_ko(stand, assigned)
    r32_o, r16_o, qf_o = display_orders()
    champ = ko["CHAMP"]

    P = []
    P.append(f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>FIFA World Cup 2026 — Model Bracket</title><style>{CSS}</style></head><body>")
    # header
    P.append("<header><div class='wrap'><h1>FIFA WORLD CUP 2026 — MODEL PREDICTION BRACKET</h1>"
             "<div class='sub'>Negative-Binomial / Dixon–Coles engine · favourite-advances path · "
             "predicted regular-time scorelines</div>"
             f"<div class='champ-banner'><span class='crown'>👑</span><div><span>Predicted champion</span><br>"
             f"<b>{esc(champ)}</b></div><span>&nbsp;·&nbsp;{BF['champion'][0][1]:.0f}% in 20k simulations</span></div>"
             "</div></header>")
    P.append("<div class='wrap'>")

    # bonusfragen panel
    P.append("<h2>Bonusfragen</h2><div class='panel'>")
    champ_rows = "".join(
        f"<div class='row'><span class='{'fav' if i==0 else ''}'>{esc(t)}</span><span class='p'>{p:.0f}%</span></div>"
        for i, (t, p) in enumerate(BF["champion"][:6]))
    P.append(f"<div class='card'><h3>Weltmeister</h3>{champ_rows}"
             f"<div class='dark'>🐎 Dark horse: <b>{esc(BF['champion_dark'][0])}</b> ({BF['champion_dark'][1]:.0f}%) — "
             f"less crowded than Spain/Argentina</div></div>")
    sf_rows = "".join(f"<div class='row'><span>{esc(t)}</span><span class='p'>{p:.0f}%</span></div>" for t, p in BF["sf"])
    P.append(f"<div class='card'><h3>Halbfinalisten (pick 4)</h3>{sf_rows}"
             f"<div class='dark'>🐎 Swap-in: <b>{esc(BF['sf_dark'][0])}</b> ({BF['sf_dark'][1]:.0f}%)</div></div>")
    P.append(f"<div class='card'><h3>Torschützenkönig-Team</h3>"
             f"<div class='row'><span class='fav'>{esc(BF['scorer'][0])}</span><span class='p'>{BF['scorer'][1]:.0f}%</span></div>"
             f"<div class='dark'>🐎 Dark horse: <b>{esc(BF['scorer_dark'][0])}</b> ({BF['scorer_dark'][1]:.0f}%)</div></div>")
    P.append("</div>")

    # groups
    P.append("<h2>Group stage — predicted standings</h2><div class='groups'>")
    for g in sorted(stand):
        rows = ""
        for pos, team in enumerate(stand[g], 1):
            cls, tag = "", ""
            if pos == 1: cls, tag = "adv", "<span class='tag w'>WIN</span>"
            elif pos == 2: cls, tag = "adv", "<span class='tag r'>R-UP</span>"
            elif pos == 3 and g in qualified: cls, tag = "third", "<span class='tag q'>3rd ✓</span>"
            rows += f"<tr class='{cls}'><td class='pos'>{pos}</td><td>{esc(team)}{tag}</td></tr>"
        P.append(f"<div class='grp'><div class='gh'>Group {g}</div><table>{rows}</table></div>")
    P.append("</div>")

    # bracket
    P.append("<h2>Knockout bracket</h2><div class='bracket'>")
    P.append("<div class='round'><div class='rh'>Round of 32</div>" +
             "".join(match_html(ko["R32"][i]) for i in r32_o) + "</div>")
    P.append("<div class='round'><div class='rh'>Round of 16</div>" +
             "".join(match_html(ko["R16"][i]) for i in r16_o) + "</div>")
    P.append("<div class='round'><div class='rh'>Quarter-finals</div>" +
             "".join(match_html(ko["QF"][i]) for i in qf_o) + "</div>")
    P.append("<div class='round'><div class='rh'>Semi-finals</div>" +
             "".join(match_html(m) for m in ko["SF"]) + "</div>")
    P.append("<div class='round fin'><div class='rh'>Final</div>" +
             match_html(ko["FINAL"][0]) + "</div>")
    P.append("<div class='round champ-col'><div class='rh'>Champion</div>"
             f"<div class='champ-box'><div class='crown'>🏆</div><div class='lbl'>WELTMEISTER</div>"
             f"<div class='nm'>{esc(champ)}</div></div></div>")
    P.append("</div>")

    P.append("<footer>Predicted, not actual. Scorelines are the engine's EV-optimal regular-time tips; "
             "knockout ties resolved to the higher-rated side (a.e.t.). Group winners and champion match the "
             "Monte-Carlo modal/favourite outcomes. Bonusfragen probabilities from a 20,000-run simulation.</footer>")
    P.append("</div></body></html>")

    os.makedirs("report", exist_ok=True)
    path = "report/wm2026_bracket.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(P))
    print(f"champion={champ}  best-thirds groups={sorted(qualified)}")
    print(f"✓ wrote {path}")


if __name__ == "__main__":
    main()
