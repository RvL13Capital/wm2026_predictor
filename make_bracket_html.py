#!/usr/bin/env python3
"""
Render a professional WC2026 bracket (HTML) from the model's predictions.

Every scoreline shown is the MOST-LIKELY result (arg-max of the predicted score grid), so
even games can end in draws — unlike the EV-optimal Kicktipp tip, which is points-maximising
and structurally avoids draws. Group standings are computed FROM those predicted results
(points → goal difference → goals scored → Elo), so the table and the fixtures can never
disagree (e.g. a team that wins all three is the group winner, full stop). The knockout tree
is wired through the real 2026 bracket (GROUPS / THIRD_PLACE_POOLS / R32_BRACKET / R16_BRACKET /
QF_BRACKET / SF_BRACKET); KO matches advance the higher-win-probability side, a.e.t. if the
most-likely score is a draw. Bonusfragen %s are from this session's 20k MC run.
Output: report/wm2026_bracket.html
"""
import os, sys, html
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import predictor
import tournament_bonusfragen as tbf
import matchday_tips as mt
import schedule_context
from stadium_data import STADIUM_DATA, haversine_distance

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


def modal(grid):
    """Most-likely (ga, gb) scoreline = arg-max cell of a score grid (str or int keys)."""
    best, bx, by = -1.0, 0, 0
    for ka, row in grid.items():
        for kb, p in row.items():
            if p > best:
                best, bx, by = p, int(ka), int(kb)
    return bx, by


def win_probs(grid):
    pa = pb = 0.0
    for ka, row in grid.items():
        for kb, p in row.items():
            if int(ka) > int(kb): pa += p
            elif int(ka) < int(kb): pb += p
    return pa, pb


# ---- Group stage: all 72 games as most-likely scorelines (full matchday model) ----
def group_games():
    team2grp = {t: g for g, ts in tbf.GROUPS.items() for t in ts}
    games = {g: [] for g in tbf.GROUPS}
    for md in (1, 2, 3):
        for r in mt.run_matchday(md, 0, 42):
            ga, gb = modal(r["grid"])
            games[team2grp[r["team_a"]]].append((md, r["team_a"], r["team_b"], ga, gb))
    for g in games:
        games[g].sort()
    return games


# ---- Standings computed FROM the predicted results (so they always match the fixtures) ----
def standings_from_games(games):
    table = {}
    for g, gl in games.items():
        st = {t: {"pts": 0, "gf": 0, "ga": 0} for t in tbf.GROUPS[g]}
        for _, a, b, x, y in gl:
            st[a]["gf"] += x; st[a]["ga"] += y; st[b]["gf"] += y; st[b]["ga"] += x
            if x > y: st[a]["pts"] += 3
            elif y > x: st[b]["pts"] += 3
            else: st[a]["pts"] += 1; st[b]["pts"] += 1
        ranked = sorted(tbf.GROUPS[g],
                        key=lambda t: (st[t]["pts"], st[t]["gf"] - st[t]["ga"], st[t]["gf"], elo(t)),
                        reverse=True)
        table[g] = [(t, st[t]["pts"], st[t]["gf"] - st[t]["ga"], st[t]["gf"]) for t in ranked]
    return table


def best_thirds(table):
    thirds = {g: table[g][2] for g in table}                  # (team, pts, gd, gf) of 3rd place
    ranked = sorted(thirds.items(),
                    key=lambda kv: (kv[1][1], kv[1][2], kv[1][3], elo(kv[1][0])), reverse=True)
    qualified = {g for g, _ in ranked[:8]}
    return {g: thirds[g][0] for g in thirds}, qualified


def assign_thirds(third_team, qualified):
    """Backtracking slot solver — mirrors tournament_bonusfragen._solve_third_assignment."""
    slot_order = ["M75", "M77", "M79", "M80", "M81", "M82", "M85", "M88"]

    def solve(idx, used, asn):
        if idx == len(slot_order):
            return dict(asn)
        slot = slot_order[idx]
        for g in tbf.THIRD_PLACE_POOLS[slot]:
            if g in qualified and g not in used:
                asn[f"3_{slot}"] = third_team[g]; used.add(g)
                r = solve(idx + 1, used, asn)
                if r is not None:
                    return r
                used.discard(g); del asn[f"3_{slot}"]
        return None
    return solve(0, set(), {}) or {}


# ---- KO match: venue (altitude + travel) + xG style aware; always a decisive scoreline ----
def predict_ko(a, b, venue, team_loc, date):
    elev = STADIUM_DATA.get(venue, {}).get("elevation", 0)
    fa, fb = tbf.compute_xg_form_multipliers(a, b)                 # playing style (attack/defend)
    row = {"team_a": a, "team_b": b, "elevation": float(elev), "form_a": fa, "form_b": fb}
    for t, pre in ((a, "a"), (b, "b")):                            # travel from each side's last venue
        prev = team_loc.get(t)
        if prev and prev[0] in STADIUM_DATA and venue in STADIUM_DATA:
            row[f"travel_miles_{pre}"] = haversine_distance(prev[0], venue)
            row[f"rest_days_{pre}"] = float(max(2, (date - prev[1]).days))
            tzc = STADIUM_DATA[venue]["tz_offset"] - STADIUM_DATA[prev[0]]["tz_offset"]
            row[f"tz_crossed_{pre}"] = abs(tzc)
            row[f"direction_{pre}"] = "East" if tzc > 0 else ("West" if tzc < 0 else "None")
        if elev > 1000:                                            # altitude: hosts acclimatised, visitors not
            row[f"accl_days_{pre}"] = 10.0 if t in tbf.HOST_TEAMS else 0.0
    grid = predictor.predict_single_match(row)["grid"]
    pa, pb = win_probs(grid)
    win = a if pa >= pb else b
    conf = (pa if win == a else pb) / (pa + pb) if (pa + pb) > 0 else 0.5   # win-share of the tie
    best, ga, gb = -1.0, (1 if win == a else 0), (0 if win == a else 1)
    for ka, gr in grid.items():
        for kb, p in gr.items():
            x, y = int(ka), int(kb)
            if x != y and ((x > y) == (win == a)) and p > best:
                best, ga, gb = p, x, y
    return {"a": a, "b": b, "ga": ga, "gb": gb, "win": win, "et": False, "venue": venue, "conf": conf}


def build_ko(table, thirds_assigned):
    # each team's last group venue+date (start point for KO travel), and KO venue/date per match_id
    _, team_state = schedule_context.get_group_match_contexts()
    team_loc = {t: (s["venue"], s["date"]) for t, s in team_state.items() if s}
    sched = schedule_context.load_schedule()
    vd = {m["match_id"]: (m["venue"], datetime.strptime(m["date"], "%Y-%m-%d")) for m in sched}
    ids = {ph: sorted(m["match_id"] for m in sched if m["phase"] == ph)
           for ph in ("R32", "R16", "QF", "SF", "FINAL")}

    def resolve(slot):
        if slot.startswith("W_"): return table[slot[2:]][0][0]
        if slot.startswith("R_"): return table[slot[2:]][1][0]
        return thirds_assigned.get(slot, "TBD")

    def play(a, b, mid):
        venue, date = vd[mid]
        m = predict_ko(a, b, venue, team_loc, date)
        team_loc[a] = (venue, date); team_loc[b] = (venue, date)   # advance each side's location
        return m

    rounds = {}
    r32 = [play(resolve(A), resolve(B), ids["R32"][i]) for i, (A, B) in enumerate(tbf.R32_BRACKET)]
    rounds["R32"] = r32; w32 = [m["win"] for m in r32]
    r16 = [play(w32[i], w32[j], ids["R16"][k]) for k, (i, j) in enumerate(tbf.R16_BRACKET)]
    rounds["R16"] = r16; w16 = [m["win"] for m in r16]
    qf = [play(w16[i], w16[j], ids["QF"][k]) for k, (i, j) in enumerate(tbf.QF_BRACKET)]
    rounds["QF"] = qf; wqf = [m["win"] for m in qf]
    sf = [play(wqf[i], wqf[j], ids["SF"][k]) for k, (i, j) in enumerate(tbf.SF_BRACKET)]
    rounds["SF"] = sf; wsf = [m["win"] for m in sf]
    rounds["FINAL"] = [play(wsf[0], wsf[1], ids["FINAL"][0])]
    rounds["CHAMP"] = rounds["FINAL"][0]["win"]
    return rounds


def display_orders():
    qf_o = [i for pair in tbf.SF_BRACKET for i in pair]
    r16_o = [i for q in qf_o for i in tbf.QF_BRACKET[q]]
    r32_o = [i for r in r16_o for i in tbf.R16_BRACKET[r]]
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
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.grp{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 3px 10px rgba(0,0,0,.2)}
.grp .gh{background:#1b3a5b;color:#fff;font-weight:700;padding:7px 12px;font-size:13px;letter-spacing:.5px}
.grp table{width:100%;border-collapse:collapse;font-size:13px}
.grp td{padding:6px 10px;border-top:1px solid #eef1f5}
.grp td.pos{color:#9aa7b8;width:18px}
.grp td.pts{text-align:right;font-variant-numeric:tabular-nums;color:#5a6b80;font-weight:700;width:26px}
.grp tr.adv td{background:#eafaf1;font-weight:700;color:#0f5132}
.grp tr.third td{background:#fff8e6}
.grp .tag{float:right;font-size:10px;font-weight:700;padding:1px 6px;border-radius:8px}
.grp .tag.w{background:#0f5132;color:#fff}.grp .tag.r{background:#198754;color:#fff}.grp .tag.q{background:#f4c430;color:#3a2c00}
.fixtures{padding:8px 12px 10px;border-top:2px solid #eef1f5;background:#fbfcfe}
.mdl{font-size:9px;text-transform:uppercase;letter-spacing:.8px;color:#9aa7b8;font-weight:700;margin:6px 0 2px}
.fx{display:grid;grid-template-columns:1fr auto 1fr;gap:7px;align-items:center;font-size:11px;padding:2px 0}
.fx .ta{text-align:right}.fx .tb{text-align:left}
.fx .s{font-variant-numeric:tabular-nums;font-weight:700;color:#1b3a5b;white-space:nowrap}
.fx .fw{font-weight:800;color:#0f5132}.fx .dr{color:#9c5a00}
/* bracket */
.bracket{display:flex;gap:18px;align-items:stretch;background:#fff;border-radius:12px;padding:20px 16px;
 box-shadow:0 4px 14px rgba(0,0,0,.25);overflow-x:auto}
.round{display:flex;flex-direction:column;justify-content:space-around;min-width:172px;flex:1}
.round .rh{text-align:center;font-size:11px;font-weight:800;letter-spacing:1px;
 color:#5a6b80;text-transform:uppercase;margin-bottom:8px}
.m{background:#f7f9fc;border:1px solid #e2e8f0;border-radius:7px;margin:5px 0;overflow:hidden;font-size:12.5px}
.m .t{display:flex;justify-content:space-between;padding:5px 9px}
.m .t.win{background:#eafaf1;font-weight:800;color:#0f5132}
.m .t.lose{color:#8a97a8}
.m .t .sc{font-variant-numeric:tabular-nums;font-weight:700}
.m .et{font-size:9px;color:#9c5a00;text-align:right;padding:0 9px 3px}
.m .cf{font-size:9.5px;color:#16635a;font-weight:700;text-align:right;padding:1px 9px 0}
.champ-box .cfin{font-size:10px;font-weight:700;margin-top:4px;opacity:.8}
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


ALT_VENUES = {v for v, d in STADIUM_DATA.items() if d.get("elevation", 0) > 1000}


def match_html(m, extra=""):
    def row(team, sc, is_win):
        return f'<div class="t {"win" if is_win else "lose"}"><span>{esc(team)}</span><span class="sc">{sc}</span></div>'
    v = m.get("venue", "")
    tag = " ⛰" if v in ALT_VENUES else ""              # altitude venue marker
    conf = m.get("conf")
    cf = f'<div class="cf">{esc(m["win"])} to advance · {conf*100:.0f}%</div>' if conf is not None else ""
    ven = f'<div class="et">@ {esc(v)}{tag}</div>' if v else ""
    return (f'<div class="m {extra}">{row(m["a"], m["ga"], m["win"]==m["a"])}'
            f'{row(m["b"], m["gb"], m["win"]==m["b"])}{cf}{ven}</div>')


def main():
    games = group_games()
    table = standings_from_games(games)
    third_team, qualified = best_thirds(table)
    assigned = assign_thirds(third_team, qualified)
    ko = build_ko(table, assigned)
    r32_o, r16_o, qf_o = display_orders()
    champ = ko["CHAMP"]
    champ_pct = dict(BF["champion"]).get(champ)

    P = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>"
         "<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>FIFA World Cup 2026 — Model Bracket</title><style>{CSS}</style></head><body>"]
    pct = f"&nbsp;·&nbsp;{champ_pct:.0f}% in 20k simulations" if champ_pct else ""
    P.append("<header><div class='wrap'><h1>FIFA WORLD CUP 2026 — MODEL PREDICTION BRACKET</h1>"
             "<div class='sub'>Most-likely scorelines · altitude · travel/rest · xG playing style · "
             "standings from results · Negative-Binomial / Dixon–Coles engine</div>"
             f"<div class='champ-banner'><span class='crown'>👑</span><div><span>Predicted champion</span><br>"
             f"<b>{esc(champ)}</b></div><span>{pct}</span></div></div></header>")
    P.append("<div class='wrap'>")

    # bonusfragen
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

    # groups: standings (from results) + the 6 predicted fixtures
    P.append("<h2>Group stage — standings &amp; predicted results</h2><div class='groups'>")
    for g in sorted(table):
        rows = ""
        for pos, (team, pts, gd, gf) in enumerate(table[g], 1):
            cls, tag = "", ""
            if pos == 1: cls, tag = "adv", "<span class='tag w'>WIN</span>"
            elif pos == 2: cls, tag = "adv", "<span class='tag r'>R-UP</span>"
            elif pos == 3 and g in qualified: cls, tag = "third", "<span class='tag q'>3rd ✓</span>"
            rows += (f"<tr class='{cls}'><td class='pos'>{pos}</td><td>{esc(team)}{tag}</td>"
                     f"<td class='pts'>{pts}</td></tr>")
        fx, last_md = "", None
        for md, a, b, x, y in games[g]:
            if md != last_md:
                fx += f"<div class='mdl'>Matchday {md}</div>"; last_md = md
            wa = "fw" if x > y else ("dr" if x == y else "")
            wb = "fw" if y > x else ("dr" if x == y else "")
            fx += (f"<div class='fx'><span class='ta {wa}'>{esc(a)}</span>"
                   f"<span class='s'>{x}&ndash;{y}</span><span class='tb {wb}'>{esc(b)}</span></div>")
        P.append(f"<div class='grp'><div class='gh'>Group {g}</div><table>{rows}</table>"
                 f"<div class='fixtures'>{fx}</div></div>")
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
    P.append("<div class='round fin'><div class='rh'>Final</div>" + match_html(ko["FINAL"][0]) + "</div>")
    P.append("<div class='round champ-col'><div class='rh'>Champion</div>"
             f"<div class='champ-box'><div class='crown'>🏆</div><div class='lbl'>WELTMEISTER</div>"
             f"<div class='nm'>{esc(champ)}</div><div class='cfin'>wins final · {ko['FINAL'][0]['conf']*100:.0f}%</div></div></div>")
    P.append("</div>")

    P.append("<footer>Predicted, not actual. Scores are the model's single most-likely result, factoring in "
             "venue altitude, travel/rest, and team xG style — group games can draw; knockouts show the most-likely "
             "<em>decisive</em> score for the advancing side (⛰ = altitude venue). Standings are computed from the "
             "group results (points, GD, goals). Heat is not modelled (no per-venue temperature data). "
             "Bonusfragen probabilities from a 20,000-run Monte-Carlo simulation.</footer>")
    P.append("</div></body></html>")

    os.makedirs("report", exist_ok=True)
    with open("report/wm2026_bracket.html", "w", encoding="utf-8") as f:
        f.write("".join(P))
    # consistency self-check: group winner must be the team that won/topped its group
    print(f"champion={champ}  best-thirds groups={sorted(qualified)}")
    for g in sorted(table):
        w = table[g][0]
        print(f"  Group {g}: winner {w[0]} ({w[1]} pts, GD {w[2]:+d})")
    print("✓ wrote report/wm2026_bracket.html")


if __name__ == "__main__":
    main()
