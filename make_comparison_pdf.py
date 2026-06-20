#!/usr/bin/env python3
"""Branded MULTI-VERSION comparison sheet: Main tip + the three isolated side engines
(O/U-total, Weather/heat, Fatigue), each LABELED, side by side, in official FIFA order.

All four columns are computed read-only from the same run_matchday lambdas; the side
engines never feed back into the main tip. A flipped variant is starred only when it
beats the main tip by >= MIN_EV_MARGIN points under its own adjusted grid (a smaller
edge is a coin-flip tie-break, shown faint with ~).

Run under the venv python (has weasyprint):
    venv/bin/python3 make_comparison_pdf.py --md 2 --out data/md2_all_versions.pdf
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import prematch_alert as pa

import predictor
import matchday_tips as M
import weather_tips
import fatigue_tips as ft
import ou_total_engine as oe
import weather_engine as we
import fatigue_engine as fe
from make_tips_pdf import flag, logo_uri, HERE          # reuse branding

MIN_EV_MARGIN = 0.02


def _variant(tip, main, ev_by_tip):
    """(tip, kind) where kind in {'same','real','tie'} by EV margin vs the main tip."""
    if tip is None:
        return "—", "none"
    if tip == main:
        return tip, "same"
    marg = ev_by_tip.get(tip, 0.0) - ev_by_tip.get(main, 0.0)
    return tip, ("real" if marg >= MIN_EV_MARGIN else "tie"), marg


def build_rows(md):
    snap = os.path.join(HERE, "data", "polymarket_match_odds.json")
    mp, mx = M.load_market_snapshot(snap)
    blended = bool(mp)
    res = M.run_matchday(md, 0, 42, mp, mx)
    by_pair = {frozenset((r["team_a"], r["team_b"])): r for r in res}
    raw = pa._http_json(pa.CALENDAR_URL)
    timeline = ft.build_timeline(raw)

    rows = []
    for date_utc, local, home, away, venue in weather_tips.upcoming_fixtures():
        r = by_pair.get(frozenset((home, away)))
        if not r:
            continue
        if r["team_a"] == home:
            lh, la = r["lambda_adj_a"], r["lambda_adj_b"]
            mt = r["optimal_tip"]; main = f"{mt[0]}:{mt[1]}"
        else:
            lh, la = r["lambda_adj_b"], r["lambda_adj_a"]
            mt = r["optimal_tip"]; main = f"{mt[1]}:{mt[0]}"

        ph, ppa = predictor.TEAM_PPDA.get(home, 11.0), predictor.TEAM_PPDA.get(away, 11.0)
        temp, hum = weather_tips.fetch_forecast(venue, date_utc)

        ou = oe.ou_total_tip(lh, la, r["config"], r.get("market_total"))
        wx = we.weather_adjusted_tip(lh, la, r["config"], temp, hum, venue, ph, ppa)
        rh, mih, tzh, dh, cuh = ft.team_load(timeline, home, date_utc, venue)
        ra, mia, tza, da, cua = ft.team_load(timeline, away, date_utc, venue)
        fh, ch = fe.team_fatigue_factor(temp, hum, venue, ph, rh, mih, tzh, dh, cuh)
        fa, ca = fe.team_fatigue_factor(temp, hum, venue, ppa, ra, mia, tza, da, cua)
        fat = fe.fatigue_adjusted_tip(lh, la, r["config"], fh, fa)

        rows.append({
            "home": home, "away": away, "venue": venue, "main": main,
            "ou": _variant(ou["tip"] if ou else None, main, ou["ev_by_tip"] if ou else {}),
            "wx": _variant(wx["tip"], main, wx["ev_by_tip"]),
            "fat": _variant(fat["tip"], main, fat["ev_by_tip"]),
            "wbgt": wx["wbgt"], "roof": wx["roof"],
            "temp": temp, "hum": hum,
            "rest": f"{rh:.0f}/{ra:.0f}", "miles": f"{mih:.0f}/{mia:.0f}",
            "fac": f"{fh:.2f}/{fa:.2f}",
        })
    return rows, blended


CSS = """
@page { size: A4 landscape; margin: 12mm 10mm; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1c1a14; margin: 0; }
.hdr { display: flex; align-items: center; gap: 12px; border-bottom: 2px solid #b89630; padding-bottom: 8px; }
.crest { width: 46px; height: 46px; object-fit: contain; }
.crest.fallback { width: 46px; height: 46px; border-radius: 50%; background: #1c1a14; color: #e9d9a3;
  font: 700 16px Georgia, serif; display: flex; align-items: center; justify-content: center; }
.hdr h1 { font: 700 19px Georgia, serif; margin: 0; }
.hdr .sub { font-size: 10px; color: #6b6450; margin-top: 2px; }
.legend { font-size: 9.5px; color: #4a4636; margin: 8px 0 6px; line-height: 1.5; }
.legend b { color: #1c1a14; }
table { border-collapse: collapse; width: 100%; font-size: 11px; }
th { background: #1c1a14; color: #e9d9a3; font: 700 10px Georgia, serif; padding: 6px 5px; text-align: center; }
td { padding: 5px 5px; border-bottom: 1px solid #eee5cc; text-align: center; }
tr:nth-child(even) td { background: #fcf9f0; }
td.match { text-align: left; white-space: nowrap; }
.flag { width: 17px; height: 12px; object-fit: cover; vertical-align: middle; border: 0.5px solid #ccc; margin: 0 3px; }
.code { font: 700 9px sans-serif; background: #eee; border-radius: 2px; padding: 0 2px; margin: 0 3px; }
.main { font: 700 13px Georgia, serif; background: #f3ead0 !important; }
.v { font-weight: 700; }
.same { color: #b3ac97; font-weight: 400; }
.real { color: #1c1a14; }
.real .star { color: #b89630; }
.tie { color: #b3ac97; font-weight: 400; }
.ctx { font-size: 9px; color: #6b6450; white-space: nowrap; }
.hot { color: #c0392b; font-weight: 700; }
.roofed { color: #2c7; }
.foot { font-size: 8.5px; color: #8a836b; margin-top: 8px; line-height: 1.4; }
"""


def cell(variant):
    if variant[1] == "none":
        return '<td class="same">—</td>'
    tip = variant[0]
    if variant[1] == "same":
        return f'<td class="same">{tip}</td>'
    marg = variant[2]
    if variant[1] == "real":
        return f'<td class="v real">{tip}&hairsp;<span class="star">★</span><br><span class="ctx">Δev {marg:+.2f}</span></td>'
    return f'<td class="v tie">{tip}~<br><span class="ctx">Δev {marg:+.2f}</span></td>'


def build_html(rows, md, blended):
    logo = logo_uri()
    crest = (f'<img class="crest" src="{logo}">' if logo else '<div class="crest fallback">vLC</div>')
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blend = "live market-blended (Polymarket)" if blended else "Elo + context (no market feed)"

    trs = []
    for i, r in enumerate(rows, 1):
        if r["roof"]:
            ctx = f'<span class="roofed">Dach zu</span> · {r["venue"]}'
        elif r["wbgt"] and r["wbgt"] > 26:
            ctx = f'<span class="hot">WBGT {r["wbgt"]:.0f}°</span> · {r["venue"]}'
        else:
            wb = f'WBGT {r["wbgt"]:.0f}°' if r["wbgt"] is not None else ""
            ctx = f'{wb} · {r["venue"]}'
        trs.append(
            f'<tr><td class="num">{i}</td>'
            f'<td class="match">{r["home"]}{flag(r["home"])} <span class="same">v</span> {flag(r["away"])}{r["away"]}</td>'
            f'<td class="main">{r["main"]}</td>'
            f'{cell(r["ou"])}{cell(r["wx"])}{cell(r["fat"])}'
            f'<td class="ctx">{ctx}<br>Pause {r["rest"]} · {r["miles"]} mi · f {r["fac"]}</td></tr>'
        )

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="hdr">{crest}<div><h1>WM 2026 — Matchday {md} — Alle Versionen</h1>
<div class="sub">{stamp} · {blend} · offizielle FIFA-Reihenfolge · ★ = echtes Signal (Δev ≥ {MIN_EV_MARGIN}), ~ = Münzwurf</div></div></div>
<div class="legend">
<b>Main</b> = EV-optimaler 4/3/2-Tipp aus dem 1X2-Markt-Blend (80/20) + Kontext — die maßgebliche Empfehlung. &nbsp;
<b>O/U</b> = Tor-Total an Polymarkts Over/Under geknüpft, Abstand erhalten (nie gekappt). &nbsp;
<b>Wetter</b> = Hitze-Ermüdung (WBGT × Pressing) → weniger Tore. &nbsp;
<b>Fatigue</b> = Hitze × Reise × Stau, differenziell (kippt enge Spiele — greift v. a. im K.o.).
</div>
<table>
<tr><th>#</th><th>Spiel (offiziell)</th><th>Main</th><th>O/U</th><th>Wetter</th><th>Fatigue</th><th>Kontext</th></tr>
{''.join(trs)}
</table>
<div class="foot">Die drei Seiten-Engines sind read-only Lesarten — sie verändern den Main-Tipp nicht. In der Gruppenphase ≈ Fatigue = Wetter (≈6 Tage Pause dämpfen Reise/Stau).
Modellannahmen: heat_accl=0, Dach=geschlossen; F9: Kontext-Terme historisch punkteneutral (Hypothesen-Fenster).</div>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", type=int, default=2)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(HERE, "data", f"md{args.md}_all_versions.pdf")
    rows, blended = build_rows(args.md)
    html = build_html(rows, args.md, blended)
    from weasyprint import HTML
    HTML(string=html, base_url=HERE).write_pdf(out)
    print(f"✅ wrote {out}  ({len(rows)} fixtures, 4 versions, logo={'embedded' if logo_uri() else 'fallback'})")


if __name__ == "__main__":
    main()
