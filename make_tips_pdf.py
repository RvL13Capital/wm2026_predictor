#!/usr/bin/env python3
"""
Render the matchday tip sheet + Bonusfragen to a branded "von Linck Capital" PDF.

Real flag IMAGES (flagcdn, cached to assets/flags/) — emoji flags don't render in weasyprint.
The Wappen logo is read from assets/wappen.png (drop yours there); falls back to a gold monogram.

    python3 make_tips_pdf.py [bonus.json] [out.pdf]                # EV-optimal sheet
    python3 make_tips_pdf.py [bonus.json] [out.pdf] --differential # both-teams-score / pool-play sheet
    python3 make_tips_pdf.py [bonus.json] [out.pdf] --master       # EV tip + modal-snipe dashboard
"""
import base64
import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone

import matchday_tips as M
import predictor

HERE = os.path.dirname(os.path.abspath(__file__))
MARKET_BLENDED = False   # set by md1_tips(): True only when a live snapshot was blended

ASSETS = os.path.join(HERE, "assets")
FLAGDIR = os.path.join(ASSETS, "flags")

# engine canonical name -> flagcdn ISO code (home nations use gb-eng / gb-sct)
FLAG = {
    "Mexico": "mx", "South Africa": "za", "South Korea": "kr", "Czechia": "cz",
    "Canada": "ca", "Bosnia": "ba", "Qatar": "qa", "Switzerland": "ch", "Brazil": "br",
    "Morocco": "ma", "Haiti": "ht", "Scotland": "gb-sct", "USA": "us", "Paraguay": "py",
    "Australia": "au", "Turkey": "tr", "Germany": "de", "Curaçao": "cw", "Ivory Coast": "ci",
    "Ecuador": "ec", "Netherlands": "nl", "Japan": "jp", "Sweden": "se", "Tunisia": "tn",
    "Belgium": "be", "Egypt": "eg", "Iran": "ir", "New Zealand": "nz", "Spain": "es",
    "Cape Verde": "cv", "Saudi Arabia": "sa", "Uruguay": "uy", "France": "fr", "Senegal": "sn",
    "Iraq": "iq", "Norway": "no", "Argentina": "ar", "Algeria": "dz", "Austria": "at",
    "Jordan": "jo", "Portugal": "pt", "DR Congo": "cd", "Uzbekistan": "uz", "Colombia": "co",
    "England": "gb-eng", "Croatia": "hr", "Ghana": "gh", "Panama": "pa",
}
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _flag_uri(code):
    os.makedirs(FLAGDIR, exist_ok=True)
    path = os.path.join(FLAGDIR, f"{code}.png")
    if not os.path.exists(path):
        url = f"https://flagcdn.com/w80/{code}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=_CTX, timeout=30) as r:
            open(path, "wb").write(r.read())
    b = base64.b64encode(open(path, "rb").read()).decode()
    return f"data:image/png;base64,{b}"


def flag(team):
    code = FLAG.get(team)
    if code:
        try:
            return f'<img class="flag" src="{_flag_uri(code)}" alt="">'
        except Exception:
            pass
    return f'<span class="code">{team[:3].upper()}</span>'


def logo_uri():
    for name, mime in (("wappen.png", "png"), ("wappen.jpg", "jpeg"), ("wappen.jpeg", "jpeg")):
        p = os.path.join(ASSETS, name)
        if os.path.exists(p):
            return f"data:image/{mime};base64," + base64.b64encode(open(p, "rb").read()).decode()
    return None


def _ev(grid, tx, ty):
    return sum(grid[a][b] * predictor.get_points(tx, ty, a, b, pts_exact=4, pts_diff=3, pts_tend=2)
               for a in grid for b in grid[a])


def md1_tips():
    """Each row: (home, away, opt_h, opt_a, opt_ev, btts_h, btts_a, btts_ev, mode_h, mode_a, mode_p).
    opt = EV-max tip (safe); btts = EV-max both-teams-score line (differential); mode = the single
    most-likely exact score from the NB grid (the 'snipe' — argmax, not an EV object)."""
    snap_path = os.path.join(HERE, "data", "polymarket_match_odds.json")
    if os.path.exists(snap_path):
        mp, mx = M.load_market_snapshot(snap_path)
    else:
        # No market snapshot available (e.g. sandboxed container): render the
        # pure Elo+stack tips — the same fallback every other consumer uses.
        print("ℹ no data/polymarket_match_odds.json — rendering Elo-only tips", file=sys.stderr)
        mp, mx = None, None
    global MARKET_BLENDED
    MARKET_BLENDED = bool(mp)
    out = []
    for r in M.run_matchday(1, 0, 42, mp, mx):
        a, b, tip, g = r["team_a"], r["team_b"], r["optimal_tip"], r["grid"]
        bt = max(((x, y) for x in range(7) for y in range(7) if x >= 1 and y >= 1),
                 key=lambda t: _ev(g, *t))
        mh, ma = max(((x, y) for x in g for y in g[x]), key=lambda t: g[t[0]][t[1]])
        out.append((a, b, tip[0], tip[1], r["ev"], bt[0], bt[1], _ev(g, *bt), mh, ma, g[mh][ma]))
    return out


def load_bonus(path):
    raw = open(path).read()
    return json.loads(raw[raw.index("{"):])


def load_goldenboot():
    """The market-blended Golden Boot top-N from goalscorer.py (data/goldenboot.json); None if absent."""
    p = os.path.join(HERE, "data", "goldenboot.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def build_html(tips, bonus, mode="optimal", goldenboot=None):
    diff = (mode == "differential")
    master = (mode == "master")
    logo = logo_uri()
    brand = (f'<img class="crest" src="{logo}">' if logo
             else '<div class="crest fallback">vLC</div>')
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blend_label = "live market-blended" if MARKET_BLENDED else "Elo + full context stack (no market feed)"

    opt_total = sum(t[4] for t in tips)
    btts_total = sum(t[7] for t in tips)
    n = len(tips)

    if master:
        body, ndiff, ndraw = [], 0, 0
        for i, (a, b, oh, oa, oev, bh, ba_, bev, mh, ma, mpr) in enumerate(tips, 1):
            differ = (mh, ma) != (oh, oa)
            cls = ("snipe draw" if (differ and mh == ma) else "snipe") if differ else ""
            ndiff += differ; ndraw += (differ and mh == ma)
            body.append(
                f'<tr><td class="num">{i}</td>'
                f'<td class="mt">{a}{flag(a)}<span class="vs">v</span>{flag(b)}{b}</td>'
                f'<td class="evtip">{oh}:{oa}</td><td class="exp">{oev:.2f}</td>'
                f'<td class="modal {cls}">{mh}:{ma}</td><td class="modp">{mpr*100:.1f}%</td></tr>'
            )
        table = ('<table class="master"><thead><tr><th></th><th class="lh">Match</th>'
                 '<th>EV&nbsp;Tip<small>safe / grind</small></th><th>Exp<small>pts</small></th>'
                 '<th>Modal<small>snipe</small></th><th>Mode<small>%</small></th></tr></thead><tbody>'
                 + "".join(body) + '</tbody></table>')
        title = "Matchday 1 — Master Dashboard"
        subtitle = f"EV-safe grind vs modal snipe · {blend_label} · {stamp}"
        summary = (f"<b>EV Tip</b> maximises expected points (the safe grind); <b>Modal</b> is the single "
                   f"most-likely exact score from the NB grid. {ndiff} of {n} differ "
                   f"(<span class='hot'>highlighted</span>), {ndraw} are hidden draws "
                   f"(<span class='hot'><b>bold</b></span>) — snipe those for 4-pt exacts when CHASING a "
                   f"pool; grind the EV column when LEADING. Σ EV ≈ {opt_total:.1f} pts.")
    else:
        rows = []
        for i, (a, b, oh, oa, oev, bh, ba_, bev, *_) in enumerate(tips, 1):
            ga, gb, ev = (bh, ba_, bev) if diff else (oh, oa, oev)
            rows.append(
                f'<tr><td class="num">{i}</td>'
                f'<td class="home">{a}{flag(a)}</td>'
                f'<td class="score">{ga}<span class="colon">:</span>{gb}</td>'
                f'<td class="away">{flag(b)}{b}</td>'
                f'<td class="ev">{ev:.2f}</td></tr>'
            )
        table = '<table class="tips">' + "\n".join(rows) + "</table>"
        if diff:
            title = "Matchday 1 — Differential Tips"
            subtitle = f"both-teams-score scorelines for pool play · {blend_label} · {stamp}"
            summary = (f"Σ expected ≈ {btts_total:.1f} pts (avg {btts_total/n:.2f}/match) — only "
                       f"{opt_total-btts_total:.1f} pts below the EV-optimal sheet over {n} matches. "
                       f"Each keeps the goal-difference band but adds a realistic both-teams-score line: "
                       f"far more differential variance for chasing a pool, at near-zero EV cost.")
        else:
            title = "Matchday 1 — Optimal Tips"
            subtitle = f"EV-maximised for 4-3-2 Kicktipp scoring · {blend_label} · {stamp}"
            summary = (f"Σ expected ≈ {opt_total:.1f} pts over {n} matches (avg {opt_total/n:.2f}/match). "
                       f"Tips are the points-maximising single guess, not the modal scoreline — see the "
                       f"master dashboard for the modal snipe column.")

    gw = bonus["group_winners"]
    gw_cells = "".join(
        f'<div class="gw"><span class="grp">{g}</span>{flag(v["tip"])}'
        f'<span class="gwteam">{v["tip"]}</span><span class="gwp">{v["probability"]*100:.0f}%</span></div>'
        for g, v in gw.items()
    )
    semis = bonus["semifinalists"]
    semi_cells = "".join(
        f'<div class="semi">{flag(t)}<span>{t}</span>'
        f'<em>{semis["probabilities"].get(t, 0)*100:.0f}%</em></div>'
        for t in semis["tips"]
    )
    champ = bonus["champion"]; scorer = bonus["top_scorer_team"]

    gb_html = ""
    if goldenboot:
        cells = "".join(
            f'<div class="gb"><span class="gbrank">{p["rank"]}</span>{flag(p["team"])}'
            f'<span class="gbname">{p["player"]}</span><span class="gbpct">{p["prob"]*100:.0f}%</span></div>'
            for p in goldenboot[:5]
        )
        gb_html = (
            '<h2 style="margin-top:16px;border:none;margin-bottom:7px;font-size:13px;">'
            'Golden Boot · Top Scorer (player)</h2>'
            f'<div class="gbgrid">{cells}</div>'
            '<div class="gbnote">70% Polymarket Golden Boot market + 30% structural model — the market '
            'prices team depth, so pure-Elo focal-scorer artefacts wash out. High-variance prop.</div>'
        )

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 3.0cm 1.4cm 1.7cm 1.4cm;
  @bottom-center {{ content: ""; }} }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1c1a14; margin: 0; }}
:root {{}}
.gold {{ color: #9a7a1e; }}
.hdr {{ position: fixed; top: -2.55cm; left: 0; right: 0; height: 2.2cm;
  border-bottom: 2px solid #b89630; display: flex; align-items: center; gap: 12px; }}
.hdr .crest {{ height: 1.85cm; width: auto; }}
.hdr .crest.fallback {{ height: 1.5cm; width: 1.5cm; border: 2px solid #b89630; border-radius: 50%;
  color: #9a7a1e; font: 700 22px/1.5cm Georgia, serif; text-align: center; letter-spacing: 1px; }}
.hdr .ht {{ display: flex; flex-direction: column; }}
.hdr .ht .name {{ font: 700 19px Georgia, "Times New Roman", serif; letter-spacing: 3px;
  color: #1c1a14; text-transform: uppercase; }}
.hdr .ht .sub {{ font-size: 10px; letter-spacing: 2px; color: #9a7a1e; text-transform: uppercase; }}
.ftr {{ position: fixed; bottom: -1.25cm; left: 0; right: 0; height: 1cm;
  border-top: 1px solid #d8caa0; font-size: 8.5px; color: #8a8470;
  display: flex; justify-content: space-between; align-items: center; }}
.ftr .pg::after {{ content: counter(page) " / " counter(pages); }}
h1 {{ font: 700 22px Georgia, serif; margin: 0 0 2px; }}
.subtitle {{ color: #9a7a1e; font-size: 11px; letter-spacing: 1px; margin-bottom: 14px;
  text-transform: uppercase; }}
table.tips {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
table.tips td {{ padding: 5.5px 6px; border-bottom: 1px solid #eee5cc; vertical-align: middle; }}
table.tips tr:nth-child(even) {{ background: #fcf9f0; }}
.num {{ color: #b8a978; width: 22px; text-align: right; font-size: 10px; }}
.home {{ text-align: right; }} .away {{ text-align: left; }}
.home, .away {{ width: 39%; font-weight: 600; }}
img.flag {{ height: 13px; width: 20px; object-fit: cover; vertical-align: middle;
  box-shadow: 0 0 0 0.5px #ccc; border-radius: 2px; }}
.home img.flag {{ margin-left: 8px; }} .away img.flag {{ margin-right: 8px; }}
.code {{ font-size: 9px; color: #888; }}
.score {{ text-align: center; font: 700 14px Georgia, serif; width: 64px;
  background: #1c1a14; color: #e9d9a3; border-radius: 4px; }}
.score .colon {{ color: #b89630; margin: 0 2px; }}
.ev {{ text-align: right; color: #b8a978; font-size: 10px; width: 34px; }}
.summary {{ margin-top: 10px; font-size: 10px; color: #8a8470; }}
.summary .hot {{ color: #c0392b; }}
table.master {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
table.master th {{ font: 700 8.5px/1.3 Georgia, serif; letter-spacing: 1px; text-transform: uppercase;
  color: #9a7a1e; border-bottom: 2px solid #b89630; padding: 4px 6px; text-align: center; }}
table.master th.lh {{ text-align: left; }}
table.master th small {{ display: block; font-weight: 400; font-size: 7px; color: #b8a978; letter-spacing: 1px; }}
table.master td {{ padding: 5px 6px; border-bottom: 1px solid #eee5cc; text-align: center; vertical-align: middle; }}
table.master tr:nth-child(even) td {{ background: #fcf9f0; }}
table.master td.mt {{ text-align: left; font-weight: 600; font-size: 11px; white-space: nowrap; }}
table.master td.mt .vs {{ color: #b8a978; font-weight: 400; margin: 0 6px; }}
table.master td.mt img.flag {{ margin: 0 5px; }}
table.master td.evtip {{ font: 700 13px Georgia, serif; }}
table.master td.exp {{ color: #b8a978; font-size: 10px; }}
table.master td.modal {{ font: 700 13px Georgia, serif; color: #1c1a14; }}
table.master td.modal.snipe {{ color: #c0392b; }}
table.master td.modal.snipe.draw {{ background: #fdecea; border-radius: 4px; }}
table.master td.modp {{ color: #8a8470; font-size: 10px; }}
h2 {{ font: 700 15px Georgia, serif; margin: 22px 0 10px; padding-bottom: 5px;
  border-bottom: 2px solid #b89630; letter-spacing: 1px; }}
.headline {{ display: flex; gap: 14px; margin-bottom: 16px; }}
.hl {{ flex: 1; border: 1px solid #e3d6a8; border-radius: 8px; padding: 12px 14px;
  background: linear-gradient(180deg,#fdfbf3,#f7efd8); }}
.hl .lbl {{ font-size: 9.5px; letter-spacing: 2px; color: #9a7a1e; text-transform: uppercase; }}
.hl .team {{ font: 700 17px Georgia, serif; margin-top: 5px; display: flex; align-items: center; gap: 8px; }}
.hl .pct {{ font-size: 10px; color: #8a8470; margin-top: 2px; }}
.gwgrid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }}
.gw {{ display: flex; align-items: center; gap: 7px; font-size: 11.5px; padding: 6px 9px;
  border: 1px solid #eee5cc; border-radius: 6px; background: #fcf9f0; }}
.gw .grp {{ font: 700 11px Georgia, serif; color: #fff; background: #b89630; width: 17px; height: 17px;
  border-radius: 50%; text-align: center; line-height: 17px; }}
.gw .gwteam {{ flex: 1; font-weight: 600; }} .gw .gwp {{ color: #b8a978; font-size: 9.5px; }}
.semis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; }}
.semi {{ text-align: center; border: 1px solid #e3d6a8; border-radius: 8px; padding: 11px 6px;
  background: #fdfbf3; }}
.semi img.flag {{ height: 18px; width: 27px; display: block; margin: 0 auto 6px; }}
.semi span {{ font-weight: 600; font-size: 12px; display: block; }}
.semi em {{ font-style: normal; font-size: 9.5px; color: #9a7a1e; }}
.gbgrid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; }}
.gb {{ position: relative; text-align: center; border: 1px solid #e3d6a8; border-radius: 8px;
  padding: 10px 4px 8px; background: #fdfbf3; }}
.gb .gbrank {{ position: absolute; top: 4px; left: 6px; font: 700 9px Georgia, serif; color: #b89630; }}
.gb img.flag {{ height: 15px; width: 23px; display: block; margin: 1px auto 5px; }}
.gb .gbname {{ display: block; font-weight: 600; font-size: 9.5px; line-height: 1.15; }}
.gb .gbpct {{ display: block; font-size: 9.5px; color: #9a7a1e; margin-top: 3px; font-weight: 700; }}
.gbnote {{ font-size: 8px; color: #8a8470; margin-top: 6px; font-style: italic; }}
</style></head><body>
<div class="hdr">{brand}<div class="ht"><span class="name">von Linck Capital</span>
  <span class="sub">Quantitative Football Intelligence</span></div></div>
<div class="ftr"><span>FIFA World Cup 2026 — Engine v-sealed · {blend_label}</span>
  <span class="pg">Page&nbsp;</span></div>

<h1>{title}</h1>
<div class="subtitle">{subtitle}</div>
{table}
<div class="summary">{summary}</div>

<h2>BONUSFRAGEN · Tournament Outright Projections</h2>
<div class="headline">
  <div class="hl"><div class="lbl">Weltmeister · Champion</div>
    <div class="team">{flag(champ['tip'])}{champ['tip']}</div>
    <div class="pct">{champ['probability']*100:.1f}% win probability ({bonus['n_sims']:,} simulations)</div></div>
  <div class="hl"><div class="lbl">Torschützenkönig · Top-Scorer Nation</div>
    <div class="team">{flag(scorer['tip'])}{scorer['tip']}</div>
    <div class="pct">{scorer['probability']*100:.1f}% to supply the Golden Boot</div></div>
</div>
{gb_html}
<h2 style="border:none;margin-bottom:8px;font-size:13px;">Group Winners</h2>
<div class="gwgrid">{gw_cells}</div>

<h2 style="margin-top:20px;border:none;margin-bottom:8px;font-size:13px;">Most Likely Semi-Finalists</h2>
<div class="semis">{semi_cells}</div>
</body></html>"""


def main():
    mode = ("master" if "--master" in sys.argv else
            "differential" if "--differential" in sys.argv else "optimal")
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    bonus_path = pos[0] if len(pos) > 0 else "/tmp/bonus.json"
    default_name = {"master": "von_linck_capital_wm2026_md1_master.pdf",
                    "differential": "von_linck_capital_wm2026_md1_differential.pdf",
                    "optimal": "von_linck_capital_wm2026_md1.pdf"}[mode]
    out = pos[1] if len(pos) > 1 else os.path.join(HERE, default_name)
    tips = md1_tips()
    bonus = load_bonus(bonus_path)
    html = build_html(tips, bonus, mode, load_goldenboot())
    from weasyprint import HTML
    HTML(string=html, base_url=HERE).write_pdf(out)
    print(f"✓ wrote {out}  ({os.path.getsize(out)//1024} KB)  mode={mode}  "
          f"logo={'embedded' if logo_uri() else 'FALLBACK monogram'}")


if __name__ == "__main__":
    main()
