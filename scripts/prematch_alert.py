#!/usr/bin/env python3
"""T-45 pre-match WhatsApp alert pipeline (ops machine, cron-driven).

For every match kicking off within --lead minutes (default 45) that has not
been alerted yet (state file), this script:

  1. fetches the OFFICIAL starting XIs from the FIFA live API (published
     ~75 min before kickoff),
  2. refreshes the Polymarket 1X2 snapshot (data/polymarket_match_odds.json),
  3. recomputes the match tip through the canonical full-stack pipeline
     (matchday_tips.run_matchday -> predictor.predict_single_match, with
     squad+injury Elo overrides and the 0.80 market blend),
  4. pushes a compact summary (tip, EV margin, model vs market 1X2, official
     XIs, current injury-Elo entries) to every CallMeBot recipient
     (utils.notify: CALLMEBOT_PHONE/APIKEY + CALLMEBOT_RECIPIENTS).

Lineups are ADVISORY in the message: the tip always comes from the committed
engine state plus the fresh market snapshot (the market blend is the
lineup-reactive channel — post-XI odds moves flow straight into the tip).
Sizing INJURY_ELO_ADJUSTMENTS stays an ops/agent decision; this script never
edits engine inputs beyond refreshing the odds snapshot file.

Cron (ops Mac, every 5 min — needs zsh env for the CallMeBot keys):
  */5 * * * * /bin/zsh -c 'source ~/.zshrc; cd ~/Desktop/wm2026_predictor && python3 scripts/prematch_alert.py --auto >> data/logs/prematch_alert.log 2>&1'

Manual:
  python3 scripts/prematch_alert.py --force-match "Canada vs Bosnia" --dry-run
"""
import argparse
import json
import os
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import predictor                      # noqa: E402
import tournament_bonusfragen as tbf  # noqa: E402
import matchday_tips                  # noqa: E402
from utils import notify              # noqa: E402

FIFA_COMPETITION = "17"
FIFA_SEASON = "285023"
CALENDAR_URL = (f"https://api.fifa.com/api/v3/calendar/matches"
                f"?idCompetition={FIFA_COMPETITION}&idSeason={FIFA_SEASON}"
                f"&count=500&language=en")
LIVE_URL_TMPL = ("https://api.fifa.com/api/v3/live/football/"
                 f"{FIFA_COMPETITION}/{FIFA_SEASON}/{{stage}}/{{match}}?language=en")
_TIMEOUT_S = 15

SCHEDULE_PATH = os.path.join(ROOT, "data", "match_schedule_2026.json")
# Live calendar refreshes land in a SEPARATE gitignored file: match statuses
# flip as games finish, and rewriting the committed file would dirty the
# worktree on every tick (same provenance hazard as the odds snapshot).
SCHEDULE_LIVE_PATH = os.path.join(ROOT, "data", "match_schedule_live.json")
# Default is the gitignored local file; the GitHub Actions cloud runner sets
# WM2026_PREMATCH_STATE=data/prematch_state_ci.json (a TRACKED file it commits
# back each run) so dedup survives across ephemeral runners without colliding
# with the ops Mac's local state.
STATE_PATH = os.environ.get(
    "WM2026_PREMATCH_STATE", os.path.join(ROOT, "data", "prematch_state.json"))
# Live snapshot is a SEPARATE, gitignored file: the ferried
# data/polymarket_match_odds.json is git-tracked, and overwriting it would
# dirty the worktree -> "(dirty)" provenance flags on every later sheet run.
SNAPSHOT_PATH = os.path.join(ROOT, "data", "polymarket_match_odds_live.json")
FERRIED_SNAPSHOT_PATH = os.path.join(ROOT, "data", "polymarket_match_odds.json")

DEFAULT_LEAD_MIN = 45     # alert when 0 < kickoff - now <= lead (T-45; official XIs are out by ~T-75)
TIP_SIMULATIONS = 1000    # same MC depth as the published sheets
TIP_SEED = 42             # pre-registered seed — keep identical to the sheets

# FIFA spellings -> engine canonical names (everything else falls through
# predictor.TEAM_NAME_MAPPING, exactly like matchday_tips.load_market_snapshot)
FIFA_NAME_ALIASES = {
    "bosnia and herzegovina": "Bosnia",
    "cabo verde": "Cape Verde",
    "congo dr": "DR Congo",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "ir iran": "Iran",
    "korea republic": "South Korea",
    "türkiye": "Turkey",
    "turkiye": "Turkey",
    "usa": "USA",
    "united states": "USA",
}

# StageName keywords -> predictor KO phase (group stage handled separately)
KO_PHASE_BY_STAGE = [
    ("round of 32", "R32"), ("round of 16", "R16"), ("quarter", "QF"),
    ("semi", "SF"), ("third", "THIRD"), ("final", "FINAL"),
]


def log(msg: str) -> None:
    print(f"[prematch {datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}",
          file=sys.stderr)


def engine_name(fifa_name: str) -> str:
    low = (fifa_name or "").strip().lower()
    if low in FIFA_NAME_ALIASES:
        return FIFA_NAME_ALIASES[low]
    return predictor.TEAM_NAME_MAPPING.get(low, (fifa_name or "").strip())


def _http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "wm2026-predictor-ops"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _atomic_write(path: str, payload: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _slim_calendar(raw: dict) -> list:
    out = []
    for m in raw.get("Results", []):
        def _team(side):
            t = m.get(side)
            if t and t.get("TeamName"):
                return t["TeamName"][0].get("Description")
            return None
        stage_name = ""
        if m.get("StageName"):
            stage_name = m["StageName"][0].get("Description", "")
        group_name = ""
        if m.get("GroupName"):
            group_name = m["GroupName"][0].get("Description", "")
        out.append({
            "id": m.get("IdMatch"),
            "stage_id": m.get("IdStage"),
            "stage": stage_name,
            "group": group_name,
            "utc": m.get("Date"),
            "home": _team("Home"),
            "away": _team("Away"),
            "status": m.get("MatchStatus"),
        })
    return out


def load_schedule(refresh: bool = True) -> list:
    """Live FIFA calendar (and persist it), falling back to the committed file.
    The live fetch keeps KO pairings current once they are known."""
    if refresh:
        try:
            slim = _slim_calendar(_http_json(CALENDAR_URL))
            if slim:
                _atomic_write(SCHEDULE_LIVE_PATH, json.dumps(slim, indent=1, ensure_ascii=False))
                return slim
        except Exception as e:   # noqa: BLE001 — cron loop must not die
            log(f"calendar fetch failed ({e}); using local fallback")
    for path in (SCHEDULE_LIVE_PATH, SCHEDULE_PATH):
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    raise FileNotFoundError(SCHEDULE_PATH)


def fetch_lineups(stage_id: str, match_id: str):
    """Official XIs from the FIFA live endpoint, or None when unpublished.
    Player Status: 1 = starting XI, 2 = substitute."""
    try:
        d = _http_json(LIVE_URL_TMPL.format(stage=stage_id, match=match_id))
    except Exception as e:   # noqa: BLE001
        log(f"lineup fetch failed for {match_id}: {e}")
        return None
    out = {}
    for side in ("HomeTeam", "AwayTeam"):
        t = d.get(side) or {}
        players = t.get("Players") or []
        xi = [(p.get("PlayerName") or [{}])[0].get("Description", "?")
              for p in players if p.get("Status") == 1]
        bench = [(p.get("PlayerName") or [{}])[0].get("Description", "?")
                 for p in players if p.get("Status") == 2]
        if len(xi) != 11:
            return None
        out["home" if side == "HomeTeam" else "away"] = {
            "xi": xi, "bench": bench, "formation": t.get("Tactics") or "?",
        }
    return out or None


def refresh_snapshot() -> str:
    """Re-fetch the Polymarket 1X2 snapshot; keep the existing file on failure."""
    try:
        from odds_client import PolymarketClient
        res = PolymarketClient().get_match_1x2_probabilities()
        if res.get("probabilities"):
            _atomic_write(SNAPSHOT_PATH, json.dumps(res, indent=2, ensure_ascii=False))
            log(f"snapshot refreshed: {len(res['probabilities'])} markets")
            return SNAPSHOT_PATH
        log("snapshot fetch returned no markets; keeping existing file")
    except Exception as e:   # noqa: BLE001
        log(f"snapshot refresh failed ({e}); keeping existing file")
    for p in (SNAPSHOT_PATH, FERRIED_SNAPSHOT_PATH):
        if os.path.exists(p):
            return p
    return None


def find_group_md(team_a: str, team_b: str):
    """Locate (md, group, oriented pair) for a group fixture; None for KO."""
    for group, teams in tbf.GROUPS.items():
        for md, matchups in (
            (1, [(teams[0], teams[1]), (teams[2], teams[3])]),
            (2, [(teams[0], teams[2]), (teams[1], teams[3])]),
            (3, [(teams[0], teams[3]), (teams[1], teams[2])]),
        ):
            for a, b in matchups:
                if {a, b} == {team_a, team_b}:
                    return md, group, (a, b)
    return None


def ko_phase(stage_name: str):
    low = (stage_name or "").lower()
    for key, phase in KO_PHASE_BY_STAGE:
        if key in low:
            return phase
    return None


def compute_group_tip(md: int, pair, snapshot_path):
    market_probs = market_extras = None
    if snapshot_path:
        market_probs, market_extras = matchday_tips.load_market_snapshot(snapshot_path)
    rows = matchday_tips.run_matchday(md, TIP_SIMULATIONS, TIP_SEED,
                                      market_probs, market_extras)
    for r in rows:
        if {r["team_a"], r["team_b"]} == set(pair):
            return r
    return None


def ko_travel_context(team_home: str, team_away: str) -> dict:
    """Per-team rest / travel / timezone + venue altitude for a KO fixture, as
    predict_single_match row fields (rest_days_{a,b}, travel_miles_{a,b},
    tz_crossed_{a,b}, direction_{a,b}, elevation, accl_days_{a,b}). The KO analogue
    of matchday_tips' group schedule-context injection, sourced from the live FIFA
    calendar Stadium/Date: a team's previous match (any prior round) → this venue.

    EXCEPTION-SAFE: any calendar-fetch / venue-resolution failure returns {} so the
    KO tip degrades to the pre-travel behaviour and the alert path never raises."""
    import datetime as _dt
    try:
        import stadium_data
        import weather_tips                       # lazy: weather_tips imports this module
        raw = _http_json(CALENDAR_URL)

        def _d(t):
            try:
                return t["TeamName"][0]["Description"]
            except Exception:
                return None

        pair = {team_home, team_away}
        tl, this = {}, None
        for m in raw.get("Results", []):
            hn, an = engine_name(_d(m.get("Home"))), engine_name(_d(m.get("Away")))
            if not hn or not an:
                continue                           # future-round slot not yet drawn
            sd = m.get("Stadium") or {}
            vk = weather_tips.venue_key((sd.get("Name") or [{}])[0].get("Description", ""))
            d = m.get("Date")
            tl.setdefault(hn, []).append((d, vk))
            tl.setdefault(an, []).append((d, vk))
            if {hn, an} == pair and this is None:
                this = (d, vk)
        if not this or not this[0]:
            return {}                              # this fixture not found / no date
        this_date, venue = this
        td = _dt.date.fromisoformat(this_date[:10])
        for t in tl:
            tl[t].sort()

        ctx = {}
        for side, team in (("a", team_home), ("b", team_away)):
            hist = [(d, v) for (d, v) in tl.get(team, []) if d and d[:10] < this_date[:10]]
            if not hist:
                ctx[f"rest_days_{side}"] = "5.0"   # no prior match -> treat as rested
                continue
            prev_d, prev_v = hist[-1]
            rest = (td - _dt.date.fromisoformat(prev_d[:10])).days
            miles = stadium_data.haversine_distance(prev_v, venue)
            tz, direction = 0, "None"
            A, B = predictor.STADIUM_DATA.get(prev_v), predictor.STADIUM_DATA.get(venue)
            if A and B:
                tz = abs(int(A.get("tz_offset", 0)) - int(B.get("tz_offset", 0)))
                direction = "east" if B["lon"] > A["lon"] else ("west" if B["lon"] < A["lon"] else "None")
            ctx[f"rest_days_{side}"] = str(float(max(0, rest)))
            ctx[f"travel_miles_{side}"] = str(float(miles))
            ctx[f"tz_crossed_{side}"] = str(int(tz))
            ctx[f"direction_{side}"] = direction

        elev = (predictor.STADIUM_DATA.get(venue, {}) or {}).get("elevation", 0)
        if elev and elev > 1000:                   # altitude only bites above 1000 m
            ctx["elevation"] = str(float(elev))
            ctx["accl_days_a"] = ctx.get("rest_days_a", "5.0")   # acclimatization ~ days since prior match
            ctx["accl_days_b"] = ctx.get("rest_days_b", "5.0")
        return ctx
    except Exception as e:
        log(f"ko_travel_context failed ({e}); KO tip computed without travel context")
        return {}


def build_ko_row(team_home: str, team_away: str, phase: str, snapshot_path) -> dict:
    """Mirror ko_tips.run_ko_round's row construction: phase + xG form
    multipliers + 0.80 market blend + KO rest/travel/altitude context. Dead-legs
    ET fatigue is the ONE deliberate omission (it needs the operator's --fatigued
    judgment call, which a T-30 cron tick does not have) — the alert discloses it."""
    row = {"team_a": team_home, "team_b": team_away, "phase": phase}
    form_a, form_b = tbf.compute_xg_form_multipliers(team_home, team_away)
    row["form_a"] = str(form_a)
    row["form_b"] = str(form_b)
    row.update(ko_travel_context(team_home, team_away))   # rest/travel/tz/altitude
    if snapshot_path:
        probs, _ = matchday_tips.load_market_snapshot(snapshot_path)
        odds = probs.get(f"{team_home}|{team_away}")
        rev = probs.get(f"{team_away}|{team_home}")
        if odds and float(odds.get("liquidity", float("inf"))) >= matchday_tips.MIN_MARKET_LIQUIDITY:
            row.update(odds_home=str(odds["1"]), odds_draw=str(odds["X"]),
                       odds_away=str(odds["2"]), market_weight="0.80")
        elif rev and float(rev.get("liquidity", float("inf"))) >= matchday_tips.MIN_MARKET_LIQUIDITY:
            row.update(odds_home=str(rev["2"]), odds_draw=str(rev["X"]),
                       odds_away=str(rev["1"]), market_weight="0.80")
    return row


def compute_ko_tip(team_home: str, team_away: str, phase: str, snapshot_path):
    row = build_ko_row(team_home, team_away, phase, snapshot_path)
    squad_adj = tbf.compute_squad_elo_adjustments() if tbf.SQUAD_MARKET_VALUES else {}
    with matchday_tips._elo_overrides(team_home, team_away, squad_adj):
        return predictor.predict_single_match(row)


def _surname(full: str) -> str:
    parts = (full or "").split()
    return " ".join(parts[1:]).title() if len(parts) > 1 else (full or "?").title()


def _grid_probs(grid: dict):
    p_h = sum(grid[a][b] for a in grid for b in grid[a] if a > b)
    p_d = sum(grid[a][b] for a in grid for b in grid[a] if a == b)
    p_a = sum(grid[a][b] for a in grid for b in grid[a] if a < b)
    return p_h * 100, p_d * 100, p_a * 100


def _reorient_tip_row(tip_row, home, away):
    """Re-express tip_row in (home, away) order so the alert matches the official
    fixture / pool home–away. Flips EVERY orientation-dependent field — tip,
    grid (drives P(model)), and the runner-up string — not just the headline, so
    a reversed fixture can never be mislabelled. No-op if already in order."""
    if not tip_row or (tip_row.get("team_a"), tip_row.get("team_b")) == (home, away):
        return tip_row
    r = dict(tip_row)
    r["team_a"], r["team_b"] = home, away
    ta, tb = tip_row["optimal_tip"]
    r["optimal_tip"] = (tb, ta)
    ng = {}
    for ga, row in (tip_row.get("grid") or {}).items():
        for gb, p in row.items():
            ng.setdefault(gb, {})[ga] = p
    r["grid"] = ng
    flipped = []
    for t in (tip_row.get("top_tips") or []):
        h, a = t["tip"].split(":")
        flipped.append(dict(t, tip=f"{a}:{h}"))
    r["top_tips"] = flipped
    return r


def _ou_tip_line(tip_row, ex, team_a, team_b):
    """The tendency-preserving O/U-coinflip tip as a compact display string, or None
    if the tip_row lacks lambdas/config or there is no usable O/U ladder. Read-only:
    consumes the message-oriented lambdas + the market O/U extras, mutates nothing.
    ex = the per-game extras dict ({'totals': [...]}) — orientation-free (a total is
    a total). See ou_total_engine.ou_adjusted_from_extras (coin-flip line + liquidity
    guard + tendency preservation: a draw stays a draw, a winner stays that winner)."""
    if not tip_row or not ex:
        return None
    la = tip_row.get("lambda_a_adj", tip_row.get("lambda_adj_a"))
    lb = tip_row.get("lambda_b_adj", tip_row.get("lambda_adj_b"))
    cfg = tip_row.get("config")
    ot = tip_row.get("optimal_tip")
    if la is None or lb is None or cfg is None or ot is None:
        return None
    try:
        import ou_total_engine as _ou
        ta, tb = (tuple(int(x) for x in ot.split(":")) if isinstance(ot, str)
                  else (int(ot[0]), int(ot[1])))
        tip, meta = _ou.ou_adjusted_from_extras(
            float(la), float(lb), cfg, ex, (ta, tb),
            ko_convention=tip_row.get("ko_convention"), team_a=team_a, team_b=team_b)
        if not meta["eligible"]:
            return "↳ O/U: keine belastbare Linie/Liquidität"
        if meta["shifted"]:
            return (f"↳ O/U-Tipp {tip[0]}:{tip[1]}  "
                    f"[Coinflip {meta['coinflip_line']}g · liq {meta['liq']/1000:.0f}k]")
        return f"↳ O/U bestätigt {ta}:{tb}  [Coinflip {meta['coinflip_line']}g]"
    except Exception:   # noqa: BLE001 — message must still go out
        return None


def build_message(match, team_a, team_b, tip_row, lineups_by_team, snapshot_path) -> str:
    """Compose the T-45 alert as a clean, sectioned, all-in-one message. team_a/team_b
    fix the orientation of EVERY number (tip, O/U tip, P(model), market). Sections:
    header · 🎯 TIPP (+ O/U-coinflip tip) · 📊 Markt · 🩹 InjElo · 🧢 Startelf."""
    ko_utc = (match.get("utc") or "")[11:16]
    label = match.get("group") or match.get("stage") or ""
    tlabel = "T-45"
    try:
        ko_dt = datetime.fromisoformat((match.get("utc") or "").replace("Z", "+00:00"))
        mins = int(round((ko_dt - datetime.now(timezone.utc)).total_seconds() / 60))
        if mins > 0:
            tlabel = f"T-{mins}"
    except Exception:
        pass

    # Load the market snapshot UP FRONT so the TIPP section can carry the O/U tip.
    # odds flipped to message orientation; ex (the O/U ladder) is orientation-free.
    # No "$" anywhere — CallMeBot swallows "$1" ("liq $1.4M" arrived as "liq .4M").
    odds = ex = None
    if snapshot_path and os.path.exists(snapshot_path):
        try:
            probs, extras = matchday_tips.load_market_snapshot(snapshot_path)
            odds = probs.get(f"{team_a}|{team_b}")
            rev = probs.get(f"{team_b}|{team_a}")
            if not odds and rev:
                odds = dict(rev, **{"1": rev["2"], "2": rev["1"]})
            ex = (extras or {}).get(f"{team_a}|{team_b}") or (extras or {}).get(f"{team_b}|{team_a}")
        except Exception:   # noqa: BLE001 — message must still go out
            odds = ex = None

    lines = [f"⚽ {tlabel} · {team_a} vs {team_b}", f"🗓 {label} · {ko_utc}Z"]

    # ── 🎯 TIPP ──
    if tip_row:
        ot = tip_row["optimal_tip"]
        ta, tb = (tuple(int(x) for x in ot.split(":")) if isinstance(ot, str)
                  else (int(ot[0]), int(ot[1])))
        lines += ["", f"🎯 TIPP  {ta}:{tb}   (EV {tip_row['ev']:.2f})"]
        ouln = _ou_tip_line(tip_row, ex, team_a, team_b)
        if ouln:
            lines.append(f"   {ouln}")
        tt = tip_row.get("top_tips") or []
        if len(tt) >= 2:
            delta = tt[0]["ev"] - tt[1]["ev"]
            strength = "STARK" if delta >= matchday_tips.EV_PLATEAU else "flach ≈Gleichstand"
            lines.append(f"   #2 {tt[1]['tip']}  (Δ{delta:.2f} · {strength})")
        p_h, p_d, p_a = _grid_probs(tip_row["grid"])
        lines.append(f"   P(Modell)  Heim {p_h:.0f}% · X {p_d:.0f}% · Ausw {p_a:.0f}%")
        mc = tip_row.get("mc")
        if mc:
            lines.append(f"   MC μ{mc['mean']:.2f} · P(0 Pkt) {mc['p0']*100:.0f}%")
        if tip_row.get("note"):
            lines.append(f"   ℹ {tip_row['note']}")
    else:
        lines += ["", "⚠ kein Tipp berechnet — Sheet manuell prüfen!"]

    # ── 📊 Markt ──
    if odds or ex:
        lines += ["", "📊 Markt (Polymarket)"]
        if odds:
            lines.append(f"   1X2  {odds['1']:.2f}/{odds['X']:.2f}/{odds['2']:.2f}"
                         f"  (liq {odds.get('liquidity', 0)/1e6:.1f}M)")
        if ex:
            mtot = ex.get("market_total")
            o25 = next((tl.get("over") for tl in (ex.get("totals") or [])
                        if tl.get("line") is not None and abs(tl["line"] - 2.5) < 0.01
                        and tl.get("over")), None)
            bits = []
            if mtot:
                bits.append(f"{mtot:.1f}g")
            if o25 and 0.0 < o25 < 1.0:
                bits.append(f"O2.5 {1.0/o25:.2f} · U2.5 {1.0/(1.0-o25):.2f}")
            if bits:
                lines.append("   O/U  " + "   ".join(bits))

    # ── 🩹 InjElo ──
    inj_a_ = tbf.INJURY_ELO_ADJUSTMENTS.get(team_a)
    inj_b_ = tbf.INJURY_ELO_ADJUSTMENTS.get(team_b)
    ia = f"{inj_a_:+.0f}" if inj_a_ else "—"
    ib = f"{inj_b_:+.0f}" if inj_b_ else "—"
    lines += ["", f"🩹 InjElo  {team_a} {ia} · {team_b} {ib}"]

    # ── 🧢 Startelf ──
    if lineups_by_team:
        lines += ["", "🧢 Startelf"]
        for t in (team_a, team_b):
            d = lineups_by_team.get(t)
            if d:
                lines.append(f"   {t} ({d['formation']}): "
                             + ", ".join(_surname(p) for p in d["xi"]))
    else:
        lines += ["", "⚠ Startelf noch nicht veröffentlicht"]

    return "\n".join(lines)


def load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:   # noqa: BLE001 — missing/corrupt state just re-baselines
        return {}


def save_state(state: dict) -> None:
    _atomic_write(STATE_PATH, json.dumps(state, indent=1))


def due_matches(schedule: list, lead_min: int, now=None) -> list:
    now = now or datetime.now(timezone.utc)
    out = []
    for m in schedule:
        if not (m.get("home") and m.get("away") and m.get("utc")):
            continue   # KO placeholder not yet resolved
        try:
            ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
        except ValueError:
            continue
        mins = (ko - now).total_seconds() / 60.0
        if 0 < mins <= lead_min:
            out.append(m)
    return out


def process_match(match, dry_run: bool = False, refresh_odds: bool = True,
                  require_xi: bool = True) -> bool:
    eng_home = engine_name(match["home"])
    eng_away = engine_name(match["away"])
    log(f"processing {eng_home} vs {eng_away} (FIFA {match['id']}, ko {match['utc']})")

    lineups = fetch_lineups(match["stage_id"], match["id"])
    if lineups is None:
        log("official XIs not available (yet)")
    lineups_by_team = None
    if lineups:
        lineups_by_team = {eng_home: lineups["home"], eng_away: lineups["away"]}

    # GATE (user policy): game alerts go out only AFTER the official starting XIs
    # are confirmed. No XI yet -> don't send, don't dedup; the 5-min runner retries
    # until FIFA publishes them (~T-75), so a delivered message always reflects the
    # final lineup. --force-match bypasses (operator override); --dry-run still prints.
    if require_xi and lineups_by_team is None and not dry_run:
        log("HOLDING alert — official starting XI not published yet; will retry next tick")
        return False

    if refresh_odds:
        snapshot_path = refresh_snapshot()
    else:
        snapshot_path = next((p for p in (SNAPSHOT_PATH, FERRIED_SNAPSHOT_PATH)
                              if os.path.exists(p)), None)

    tip_row = None
    grp = find_group_md(eng_home, eng_away)
    try:
        if grp:
            md, group, pair = grp
            tip_row = compute_group_tip(md, pair, snapshot_path)
            if tip_row and (tip_row["team_a"], tip_row["team_b"]) != (eng_home, eng_away):
                log(f"note: engine orients this fixture as "
                    f"{tip_row['team_a']} vs {tip_row['team_b']}")
        else:
            phase = ko_phase(match.get("stage", ""))
            if phase:
                res = compute_ko_tip(eng_home, eng_away, phase, snapshot_path)
                # adapt predict_single_match dict to the message fields we use
                grid = {int(ga): {int(gb): float(p) for gb, p in row.items()}
                        for ga, row in res["grid"].items()}
                tip = tuple(int(x) for x in res["optimal_tip"].split(":"))
                tip_row = {"team_a": eng_home, "team_b": eng_away, "grid": grid,
                           "optimal_tip": tip, "ev": res["ev"],
                           "top_tips": res.get("top_tips", []), "mc": None,
                           # lambdas/config carried in message (eng_home/away) orientation
                           # so build_message can add the O/U-coinflip tip (no reorient here).
                           "lambda_a_adj": res.get("lambda_a_adj"),
                           "lambda_b_adj": res.get("lambda_b_adj"),
                           "config": res.get("config"),
                           "ko_convention": res.get("ko_convention"),
                           "note": "KO quick path: no fatigue flags — ko_tips sheet authoritative"}
            else:
                log(f"cannot classify stage '{match.get('stage')}' — no tip path")
    except Exception as e:   # noqa: BLE001 — always still send something
        log(f"tip computation failed: {e}")

    # Present in the OFFICIAL fixture order (eng_home vs eng_away) so the WhatsApp
    # matches the pool's home–away and is enter-ready. _reorient_tip_row flips
    # EVERY field (tip, grid->P(model), runner-up) for a reversed fixture, so the
    # numbers can never be mislabelled (build_message still trusts team_a/team_b).
    tip_row = _reorient_tip_row(tip_row, eng_home, eng_away)
    team_a, team_b = eng_home, eng_away
    msg = build_message(match, team_a, team_b, tip_row, lineups_by_team, snapshot_path)
    print(msg)
    if dry_run:
        log("dry-run: not sending")
        return True
    sent = notify.send_whatsapp(msg)
    log(f"WhatsApp sent={sent} (configured={notify.is_configured()})")
    return sent


# How far back warn_missed_alerts looks. Wide enough to catch a multi-hour daemon
# OUTAGE (PC off / asleep through a T-45 window) on the first tick after recovery —
# the in-daemon detector is useless while the daemon is down, so on restart it must
# look back far enough to surface anything missed during the blackout. 12h covers an
# overnight off; older fixtures are already settled and out of scope.
MISS_LOOKBACK_MIN = 720.0


def warn_missed_alerts(schedule: list, state: dict) -> None:
    """Surface — by LOG and an active WhatsApp ping — any fixture that kicked off in the
    last MISS_LOOKBACK_MIN minutes WITHOUT ever being alerted. Two causes this catches:
    (1) a late XI the T-45 gate held past kickoff; (2) a daemon/PC OUTAGE that swallowed
    the whole window (the real Switzerland-Bosnia miss on 2026-06-18). Warns ONCE per
    fixture (recorded as miss:<id>). The WhatsApp ping means the operator is told even if
    nobody is reading the log — essential for MD3 overnight doubles."""
    now = datetime.now(timezone.utc)
    changed = False
    for m in schedule:
        if not (m.get("home") and m.get("away") and m.get("utc")):
            continue
        try:
            ko = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
        except ValueError:
            continue
        mins = (ko - now).total_seconds() / 60.0
        mk = f"miss:{m['id']}"
        if -MISS_LOOKBACK_MIN < mins <= 0.0 and str(m["id"]) not in state and mk not in state:
            msg = (f"⚠ MISSED ALERT: {m['home']} vs {m['away']} kicked off "
                   f"{abs(mins):.0f}m ago with NO T-45 alert sent "
                   f"(late XI, or daemon/PC down in its window — enter this one manually)")
            log(msg)
            try:
                notify.send_whatsapp(msg)   # actively ping; don't rely on log-reading
            except Exception:               # noqa: BLE001 — a flag must never crash the tick
                pass
            state[mk] = now.isoformat(timespec="seconds")
            changed = True
    if changed:
        save_state(state)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T-45 pre-match WhatsApp alerts")
    ap.add_argument("--auto", action="store_true",
                    help="cron mode: alert every due, not-yet-alerted match")
    ap.add_argument("--lead", type=int, default=DEFAULT_LEAD_MIN,
                    help="alert window in minutes before kickoff")
    ap.add_argument("--force-match", type=str, default=None,
                    help='ignore window/state for one fixture, e.g. "Canada vs Bosnia"')
    ap.add_argument("--dry-run", action="store_true", help="print, do not send")
    ap.add_argument("--no-odds-refresh", action="store_true",
                    help="use the existing snapshot file (offline/test)")
    args = ap.parse_args(argv)

    schedule = load_schedule(refresh=not args.no_odds_refresh)

    if args.force_match:
        want = {engine_name(t.strip()) for t in args.force_match.split(" vs ")}
        for m in schedule:
            if m.get("home") and m.get("away") and \
                    {engine_name(m["home"]), engine_name(m["away"])} == want:
                ok = process_match(m, dry_run=args.dry_run,
                                   refresh_odds=not args.no_odds_refresh,
                                   require_xi=False)  # operator override: may send pre-XI
                return 0 if ok else 1
        log(f"fixture not found in schedule: {args.force_match}")
        return 2

    if not args.auto:
        ap.print_help()
        return 0

    state = load_state()
    warn_missed_alerts(schedule, state)   # no-silent-skip safety net (esp. MD3 doubles)
    due = due_matches(schedule, args.lead)
    if not due:
        log("no matches in window")
        return 0
    rc = 0
    for m in due:
        if str(m["id"]) in state:
            continue
        # Per-match isolation: one game's unexpected failure must NEVER skip the other
        # simultaneous game (MD3 doubles). Defence-in-depth independent of notify's
        # never-raise contract — a crash here just drops THIS match to retry next tick.
        try:
            ok = process_match(m, dry_run=args.dry_run,
                               refresh_odds=not args.no_odds_refresh)
        except Exception as e:   # noqa: BLE001
            log(f"process_match crashed for {m.get('home')} vs {m.get('away')}: {e}")
            ok = False
        if ok and not args.dry_run:
            state[str(m["id"])] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_state(state)
        rc = rc if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
