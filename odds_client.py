#!/usr/bin/env python3
"""
Market Odds Client — Fetches and normalizes betting odds from multiple sources.

Supported sources:
  1. The Odds API (traditional bookmakers — requires free API key)
  2. Polymarket Gamma API (prediction market — no auth needed)
  3. Manual decimal odds input

Usage:
    from odds_client import OddsClient
    
    client = OddsClient(odds_api_key="your_key")  # Optional
    probs = client.get_match_probabilities("Germany", "Japan")
    # Returns: {"p_home": 0.45, "p_draw": 0.28, "p_away": 0.27, "source": "odds_api"}
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import urllib.request
    import urllib.error
    import urllib.parse
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

@dataclass
class MatchOdds:
    """Normalized match odds from any source."""
    p_home: float
    p_draw: float
    p_away: float
    source: str  # "odds_api", "polymarket", "manual"
    bookmaker: str = "market"
    timestamp: str = ""
    raw_odds_home: float = 0.0
    raw_odds_draw: float = 0.0
    raw_odds_away: float = 0.0
    overround: float = 0.0  # Market margin (e.g., 0.05 = 5%)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "p_home": round(self.p_home, 4),
            "p_draw": round(self.p_draw, 4),
            "p_away": round(self.p_away, 4),
            "source": self.source,
            "bookmaker": self.bookmaker,
            "timestamp": self.timestamp,
            "overround": round(self.overround, 4),
        }


# ==============================================================================
# VIG STRIPPING (Margin Removal)
# ==============================================================================

def strip_vig(raw_home: float, raw_draw: float, raw_away: float) -> Tuple[float, float, float]:
    """
    Removes bookmaker margin (vig/overround) from implied probabilities.
    
    Method: Basic normalization — divide each probability by the sum.
    This is the most common approach and works well for 3-way markets.
    
    Args:
        raw_home/draw/away: Raw implied probabilities (sum > 1.0)
    
    Returns:
        Fair (p_home, p_draw, p_away) that sum to 1.0
    """
    total = raw_home + raw_draw + raw_away
    if total <= 0:
        raise ValueError(f"Invalid raw probabilities: sum={total}")
    return (raw_home / total, raw_draw / total, raw_away / total)


def decimal_odds_to_probabilities(odds_home: float, odds_draw: float, 
                                   odds_away: float) -> MatchOdds:
    """
    Converts decimal (European) odds to fair probabilities with vig removed.
    
    Decimal odds: 1.85 means "bet 1€, get 1.85€ back" (0.85€ profit).
    Implied probability = 1 / decimal_odds.
    
    Args:
        odds_home: Decimal odds for home win (e.g., 1.85)
        odds_draw: Decimal odds for draw (e.g., 3.40)
        odds_away: Decimal odds for away win (e.g., 4.50)
    
    Returns:
        MatchOdds with fair probabilities (vig stripped)
    """
    if odds_home <= 1.0 or odds_draw <= 1.0 or odds_away <= 1.0:
        raise ValueError(f"Decimal odds must be > 1.0. Got: {odds_home}, {odds_draw}, {odds_away}")
    
    raw_home = 1.0 / odds_home
    raw_draw = 1.0 / odds_draw
    raw_away = 1.0 / odds_away
    
    overround = (raw_home + raw_draw + raw_away) - 1.0
    
    p_home, p_draw, p_away = strip_vig(raw_home, raw_draw, raw_away)
    
    return MatchOdds(
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        source="manual",
        bookmaker="user_input",
        raw_odds_home=odds_home,
        raw_odds_draw=odds_draw,
        raw_odds_away=odds_away,
        overround=overround,
    )


# ==============================================================================
# THE ODDS API CLIENT
# ==============================================================================

class OddsAPIClient:
    """
    Fetches odds from The Odds API (https://the-odds-api.com).
    Free tier: 500 requests/month. Covers major football competitions.
    """
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    SPORT_KEY = "soccer_fifa_world_cup"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._remaining_requests = None
    
    def _request(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated request to The Odds API."""
        if not HAS_URLLIB:
            raise RuntimeError("urllib not available")
        
        if params is None:
            params = {}
        params["apiKey"] = self.api_key
        
        url = f"{self.BASE_URL}/{endpoint}"
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        req = urllib.request.Request(full_url)
        req.add_header("Accept", "application/json")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                # Track remaining requests
                remaining = response.headers.get("X-Requests-Remaining")
                if remaining:
                    self._remaining_requests = int(remaining)
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Odds API error {e.code}: {e.read().decode()}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Odds API connection error: {e}")
    
    def get_upcoming_odds(self, bookmakers: str = "pinnacle",
                          markets: str = "h2h") -> List[dict]:
        """
        Fetch upcoming match odds.
        
        Args:
            bookmakers: Comma-separated bookmaker keys (pinnacle, betfair, etc.)
            markets: Market types (h2h = 1x2, totals = over/under)
        """
        params = {
            "regions": "eu",
            "markets": markets,
            "bookmakers": bookmakers,
            "oddsFormat": "decimal",
        }
        return self._request(f"sports/{self.SPORT_KEY}/odds", params)
    
    def find_match_odds(self, team_a: str, team_b: str,
                        prefer_bookmaker: str = "pinnacle") -> Optional[MatchOdds]:
        """
        Find odds for a specific match by team names.
        
        Uses fuzzy matching on team names since APIs use different naming conventions.
        """
        events = self.get_upcoming_odds(bookmakers=prefer_bookmaker)
        
        team_a_lower = team_a.lower()
        team_b_lower = team_b.lower()
        
        for event in events:
            home = event.get("home_team", "").lower()
            away = event.get("away_team", "").lower()
            
            # Fuzzy match
            if (self._name_match(team_a_lower, home) and self._name_match(team_b_lower, away)) or \
               (self._name_match(team_a_lower, away) and self._name_match(team_b_lower, home)):
                
                # Find the preferred bookmaker's odds
                for bookmaker_data in event.get("bookmakers", []):
                    for market in bookmaker_data.get("markets", []):
                        if market.get("key") == "h2h":
                            outcomes = {o["name"].lower(): o["price"] for o in market.get("outcomes", [])}
                            
                            # Determine which team is home/away in the API
                            is_reversed = self._name_match(team_a_lower, away)
                            
                            odds_h = outcomes.get(home, 0)
                            odds_d = outcomes.get("draw", 0)
                            odds_a = outcomes.get(away, 0)
                            
                            if is_reversed:
                                odds_h, odds_a = odds_a, odds_h
                            
                            if odds_h > 1 and odds_d > 1 and odds_a > 1:
                                result = decimal_odds_to_probabilities(odds_h, odds_d, odds_a)
                                result.source = "odds_api"
                                result.bookmaker = bookmaker_data.get("key", "unknown")
                                return result
        
        return None
    
    @staticmethod
    def _name_match(query: str, candidate: str) -> bool:
        """Fuzzy team name matching."""
        # Direct match
        if query in candidate or candidate in query:
            return True
        # Common abbreviations
        abbreviations = {
            "usa": "united states", "us": "united states",
            "korea": "south korea", "korea republic": "south korea",
        }
        q = abbreviations.get(query, query)
        c = abbreviations.get(candidate, candidate)
        return q in c or c in q
    
    @property
    def remaining_requests(self) -> Optional[int]:
        return self._remaining_requests


# ==============================================================================
# POLYMARKET CLIENT
# ==============================================================================

THIN_LIQUIDITY = 5000.0   # USD; below this a Polymarket match line is thin -> warn (override w/ a sharp book)


def _num(m, *keys):
    """First parseable float among m[keys], else 0.0 (Polymarket sends some numbers as strings)."""
    for k in keys:
        v = m.get(k)
        try:
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            pass
    return 0.0


class PolymarketClient:
    """
    Fetches probabilities from Polymarket prediction markets.
    No authentication needed for public market data.
    
    IMPORTANT: Requires User-Agent header or Gamma API returns 403.
    
    Data format notes:
    - Per-match 1X2 games live under the **fifa-world-cup** tag as events titled "A vs. B", each
      holding three binary Yes/No legs (home-win / draw / away-win). See _extract_game_1x2.
    - The 'world-cup' tag carries ONLY outrights/group/player props -- never the match games.
    - get_wc_winner_probabilities() still reads the tournament-winner outright (bracket equity).
    """
    
    GAMMA_URL = "https://gamma-api.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    MAX_RETRIES = 4

    def _request(self, endpoint: str, params: dict = None) -> list:
        """
        GET the Gamma API with a User-Agent (required — 403 without) and retry/backoff.

        Gamma's documented limits are generous (/events 500 req/10s, /markets 300 req/10s) and it
        THROTTLES (queues) rather than returning 429, so our ~5 paged /events calls never approach
        the cap. But a daily cron still meets transient 5xx/timeouts — so back off and retry
        (honoring Retry-After) instead of crashing the operational loop.
        """
        if not HAS_URLLIB:
            raise RuntimeError("urllib not available")

        url = f"{self.GAMMA_URL}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", self.USER_AGENT)

        last = None
        for attempt in range(self.MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 500, 502, 503, 504):
                    break                                    # 4xx (bad query) — don't hammer
                wait = float(e.headers.get("Retry-After", 0) or 0) or (2 ** attempt)
                if attempt < self.MAX_RETRIES - 1:
                    print(f"[odds] HTTP {e.code} from /{endpoint}; backoff {wait:.0f}s", file=sys.stderr)
                    time.sleep(wait)
            except urllib.error.URLError as e:
                last = e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"Polymarket API error after {self.MAX_RETRIES} tries: {last}")
    
    def get_wc_winner_probabilities(self) -> Dict[str, float]:
        """
        Fetch WC 2026 tournament winner probabilities from Polymarket.
        
        Returns:
            Dict mapping team name → P(win tournament), e.g. {"France": 0.164, ...}
        """
        markets = self._request("markets", {
            "limit": 100,
            "active": "true",
            "closed": "false",
        })
        
        teams = {}
        for m in markets:
            q = m.get("question", "")
            if "win the 2026 FIFA World Cup" not in q:
                continue
            
            # Parse team name from question
            team = q.replace("Will ", "").replace(" win the 2026 FIFA World Cup?", "").strip()
            
            # Parse prices (stored as JSON string array)
            prices = m.get("outcomePrices", "[]")
            if isinstance(prices, str):
                prices = json.loads(prices)
            
            if prices:
                p_win = float(prices[0])
                if p_win > 0:
                    teams[team] = p_win
        
        return teams
    
    @staticmethod
    def _extract_game_1x2(event) -> Optional[tuple]:
        """
        Pull a 1X2 line out of ONE Polymarket game event.

        A Polymarket soccer game is an event titled "Team A vs. Team B" holding THREE binary
        Yes/No markets (negRisk group):
            groupItemTitle "Team A"                 q "Will Team A win on <date>?"      -> P(home)=YES px
            groupItemTitle "Draw (Team A vs. ...)"  q "Will A vs. B end in a draw?"     -> P(draw)=YES px
            groupItemTitle "Team B"                 q "Will Team B win on <date>?"      -> P(away)=YES px
        The 1X2 probabilities are the YES price of each leg (they sum ~1, near vig-free).

        Returns (home, away, odds_home, odds_draw, odds_away, min_leg_liq, sum_leg_vol) or None
        if the event is not a 3-leg game (this also rejects outrights/props/settled lines, so it
        doubles as the games filter — no reliance on tags).
        """
        title = (event.get("title") or "").strip()
        low = title.lower()
        # The primary moneyline event is exactly "A vs. B". Sibling markets (totals, spreads, exact
        # score, halftime) are "A vs. B - <Suffix>"; player props are "...Goals H2H: X vs. Y". A
        # " - " or "h2h" in the title marks a non-moneyline event — reject (no national team name
        # contains " - "). This isolates the 1X2 line robustly, not by accident of name-matching.
        if " vs" not in low or "h2h" in low or " - " in title:
            return None
        for sep in (" vs. ", " vs "):                       # "A vs. B" (period) or "A vs B"
            if sep in title:
                home, away = (s.strip() for s in title.split(sep, 1))
                break
        else:
            return None

        legs = {"1": None, "X": None, "2": None}            # (yes_price, liq, vol) per outcome
        for m in event.get("markets", []):
            q = (m.get("question") or "").lower()
            git = (m.get("groupItemTitle") or "").strip()
            outcomes = m.get("outcomes", "[]")
            prices = m.get("outcomePrices", "[]")
            try:
                if isinstance(outcomes, str): outcomes = json.loads(outcomes)
                if isinstance(prices, str): prices = json.loads(prices)
            except json.JSONDecodeError:
                continue
            if not outcomes or len(outcomes) != len(prices):
                continue
            try:
                yes_idx = [str(o).lower() for o in outcomes].index("yes")
                p_yes = float(prices[yes_idx])
            except (ValueError, TypeError):
                continue
            liq = _num(m, "liquidityNum", "liquidity", "liquidityClob")
            vol = _num(m, "volumeNum", "volume", "volumeClob")

            if "end in a draw" in q or git.lower().startswith("draw"):
                slot = "X"
            else:                                            # a team leg — assign by groupItemTitle/question
                who = git
                if not who and q.startswith("will ") and " win" in q:
                    who = q[5:q.index(" win")].strip()
                wl = who.lower()
                slot = "1" if wl == home.lower() else "2" if wl == away.lower() else None
            if slot and legs[slot] is None:
                legs[slot] = (p_yes, liq, vol)

        if any(v is None for v in legs.values()):
            return None
        (ph, lh, vh), (px, lx, vx), (pa, la, va) = legs["1"], legs["X"], legs["2"]
        if not (0.0 < ph < 1.0 and 0.0 < px < 1.0 and 0.0 < pa < 1.0):
            return None                                      # settled/degenerate (e.g. 1/0/0)
        if not (0.85 <= ph + px + pa <= 1.30):
            return None                                      # not a sane 3-way moneyline
        return (home, away,
                round(1.0 / ph, 3), round(1.0 / px, 3), round(1.0 / pa, 3),
                round(min(lh, lx, la), 2), round(vh + vx + va, 2))

    @staticmethod
    def _parse_pair(title):
        """('A vs. B - <Suffix>') -> ('A','B'); strips any ' - <Suffix>'. None if not a matchup."""
        base = (title or "").split(" - ", 1)[0].strip()
        for sep in (" vs. ", " vs "):
            if sep in base:
                h, a = (s.strip() for s in base.split(sep, 1))
                return h, a
        return None

    @classmethod
    def _extract_extras(cls, event):
        """
        Parse the READ-ONLY derivative markets from a game's sibling events — the totals ladder
        (O/U 0.5..5.5), Asian spreads (Team -1.5/-2.5), Both-Teams-To-Score, and the exact-score
        grid. Returns (game_key, data) keyed identically to the 1X2 ("Home|Away"), or None.

        NONE of this feeds the sealed engine. It is captured (a) for the read-only goal-total
        calibration flag in matchday_tips, and (b) to seed the historical O/U dataset a future,
        *validated* dispersion blend would need. `market_total` = E[goals] implied by the ladder.
        """
        pair = cls._parse_pair(event.get("title"))
        if not pair:
            return None
        home, away = pair
        totals, spreads, exact, btts = [], [], [], None
        for m in event.get("markets", []):
            git = (m.get("groupItemTitle") or "").strip()
            o = m.get("outcomes", "[]"); p = m.get("outcomePrices", "[]")
            try:
                if isinstance(o, str): o = json.loads(o)
                if isinstance(p, str): p = json.loads(p)
            except json.JSONDecodeError:
                continue
            if not o or len(o) != len(p):
                continue
            names = [str(x).lower() for x in o]
            liq = _num(m, "liquidityNum", "liquidity", "liquidityClob")
            gl = git.lower()
            if "over" in names and "under" in names:                       # O/U totals ladder
                try:
                    line = float(gl.replace("o/u", "").replace("over/under", "").strip())
                    totals.append({"line": line, "over": round(float(p[names.index("over")]), 4),
                                   "liq": round(liq, 2)})
                except (ValueError, IndexError):
                    pass
            elif "(" in git and ")" in git:                                # spread / handicap
                try:
                    tm = git[:git.index("(")].strip()
                    line = float(git[git.index("(") + 1:git.index(")")])
                    ci = names.index(tm.lower()) if tm.lower() in names else 0
                    spreads.append({"team": tm, "line": line, "cover": round(float(p[ci]), 4),
                                    "liq": round(liq, 2)})
                except (ValueError, IndexError):
                    pass
            elif "both teams to score" in gl and "yes" in names:           # BTTS
                btts = {"yes": round(float(p[names.index("yes")]), 4), "liq": round(liq, 2)}
            elif gl.startswith("exact score") and "yes" in names:          # exact-score grid
                sc = git.split(":", 1)[1].strip() if ":" in git else git
                exact.append({"score": sc, "prob": round(float(p[names.index("yes")]), 4),
                              "liq": round(liq, 2)})

        data = {}
        if totals:
            totals.sort(key=lambda d: d["line"])
            data["totals"] = totals
            # E[goals] = sum_k P(N > k+0.5) over the consecutive ladder from 0.5 (a lower bound: it
            # ignores the small mass above the top line). Polymarket O/U prices already sum to 1.
            mt, expect = 0.0, 0.5
            for t in totals:
                if abs(t["line"] - expect) < 1e-9:
                    mt += t["over"]; expect += 1.0
                else:
                    break
            if mt > 0:
                data["market_total"] = round(mt, 3)
        if spreads:
            data["spreads"] = spreads
        if btts:
            data["btts"] = btts
        if exact:
            exact.sort(key=lambda d: -d["prob"])
            data["exact"] = exact
        return (f"{home}|{away}", data) if data else None

    def get_match_1x2_probabilities(self, min_liquidity: float = 0.0, events=None) -> dict:
        """
        Fetch live World Cup 1X2 match markets from Polymarket as raw decimal odds, each TAGGED with
        its USD liquidity/volume so thin (noisy) markets are visible and can be overridden by hand.

        The games live under the **fifa-world-cup** tag as per-match EVENTS (NOT the 'world-cup' tag,
        which carries only outrights/props, and NOT as single 3-outcome markets). Each game event holds
        three binary Yes/No legs; see _extract_game_1x2. Lines below `min_liquidity` (thinnest leg) are
        dropped. Schema:
        { "probabilities": { "Mexico|South Africa": {"1":1.46,"X":4.88,"2":9.52,"liquidity":..,"volume":..} } }
        (Pass events=[...] to parse a fixture list offline, e.g. for tests.)
        """
        if events is None:
            events, seen = [], set()
            for off in range(0, 1500, 100):                  # paginate (WC has ~300 game events)
                page = self._request("events", {
                    "tag_slug": "fifa-world-cup", "closed": "false",
                    "limit": 100, "offset": off,
                })
                if not page:
                    break
                events.extend(e for e in page if e.get("id") not in seen)
                seen.update(e.get("id") for e in page)
                if len(page) < 100:                          # last page
                    break

        matches, extras, dropped = {}, {}, []
        for e in events:
            parsed = self._extract_game_1x2(e)               # also rejects outrights/props/settled
            if parsed:
                home, away, oh, od, oa, liq, vol = parsed
                key = f"{home}|{away}"
                if min_liquidity > 0.0 and liq < min_liquidity:
                    dropped.append((key, liq)); continue
                matches[key] = {"1": oh, "X": od, "2": oa, "liquidity": liq, "volume": vol}
            else:                                            # read-only derivatives (totals/spreads/exact)
                ex = self._extract_extras(e)
                if ex:
                    extras.setdefault(ex[0], {}).update(ex[1])
        extras = {k: v for k, v in extras.items() if k in matches}   # drop orphans (props w/o a 1X2 game)

        # operator-facing summary on stderr: which markets are thin enough to override?
        thin = sorted(((k, v["liquidity"]) for k, v in matches.items() if v["liquidity"] < THIN_LIQUIDITY),
                      key=lambda kv: kv[1])
        print(f"[odds] {len(matches)} 1X2 game markets parsed"
              + (f"; {len(extras)} with O/U+spread+exact extras" if extras else "")
              + (f"; {len(dropped)} dropped < ${min_liquidity:,.0f}" if min_liquidity > 0 else "")
              + (f"; {len(thin)} THIN (< ${THIN_LIQUIDITY:,.0f}) -- override these with a sharp book:" if thin else ""),
              file=sys.stderr)
        for k, liq in thin:
            print(f"[odds]   THIN {k}  ${liq:,.0f}", file=sys.stderr)

        return {"source": "polymarket_matches_1x2", "probabilities": matches, "extras": extras}


# ==============================================================================
# UNIFIED ODDS CLIENT
# ==============================================================================

class OddsClient:
    """
    Unified client that tries multiple sources in order:
    1. The Odds API (if API key configured)
    2. Polymarket (always available)
    3. Manual input fallback
    """
    
    def __init__(self, odds_api_key: Optional[str] = None):
        self.odds_api = OddsAPIClient(odds_api_key) if odds_api_key else None
        self.polymarket = PolymarketClient()
        self._cache: Dict[str, MatchOdds] = {}
    
    def get_match_probabilities(self, team_a: str, team_b: str,
                                 preferred_source: str = "auto") -> Optional[MatchOdds]:
        """
        Get match probabilities from the best available source.
        
        Args:
            team_a: Home team name
            team_b: Away team name
            preferred_source: "odds_api", "polymarket", "auto" (try all)
        
        Returns:
            MatchOdds or None if no source available
        """
        cache_key = f"{team_a.lower()}__{team_b.lower()}"
        
        # Check cache (valid for 30 minutes)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            cached_time = datetime.fromisoformat(cached.timestamp)
            age_seconds = (datetime.utcnow() - cached_time).total_seconds()
            if age_seconds < 1800:  # 30 min
                return cached
        
        result = None
        
        if preferred_source in ("odds_api", "auto") and self.odds_api:
            try:
                result = self.odds_api.find_match_odds(team_a, team_b)
                if result:
                    self._cache[cache_key] = result
                    return result
            except Exception as e:
                print(f"⚠ Odds API error: {e}")
        
        # per-match Polymarket lookup removed: bulk fetch via get_match_1x2_probabilities().

        return None
    
    @staticmethod
    def from_manual_odds(odds_home: float, odds_draw: float, 
                         odds_away: float) -> MatchOdds:
        """Create MatchOdds from user-provided decimal odds."""
        return decimal_odds_to_probabilities(odds_home, odds_draw, odds_away)


# ==============================================================================
# ODDS MOVEMENT TRACKER
# ==============================================================================

class OddsTracker:
    """
    Tracks odds movements over time to detect late-breaking information.
    Stores snapshots in a JSON file for historical analysis.
    """
    
    def __init__(self, storage_path: str = "data/odds_history.json"):
        self.storage_path = storage_path
        self._history: Dict[str, List[dict]] = {}
        self._load()
    
    def _load(self):
        """Load history from file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self._history = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._history = {}
    
    def _save(self):
        """Save history to file."""
        os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(self._history, f, indent=2)
    
    def snapshot(self, team_a: str, team_b: str, odds: MatchOdds):
        """Record a new odds snapshot."""
        key = f"{team_a.lower()}__{team_b.lower()}"
        if key not in self._history:
            self._history[key] = []
        self._history[key].append(odds.to_dict())
        self._save()
    
    def get_movement(self, team_a: str, team_b: str) -> Optional[dict]:
        """
        Analyze odds movement for a match.
        
        Returns:
            Dict with movement analysis, or None if insufficient data.
        """
        key = f"{team_a.lower()}__{team_b.lower()}"
        snapshots = self._history.get(key, [])
        
        if len(snapshots) < 2:
            return None
        
        first = snapshots[0]
        latest = snapshots[-1]
        
        delta_home = latest["p_home"] - first["p_home"]
        delta_draw = latest["p_draw"] - first["p_draw"]
        delta_away = latest["p_away"] - first["p_away"]
        
        # Detect significant movements (>5% shift)
        significant = abs(delta_home) > 0.05 or abs(delta_away) > 0.05
        
        return {
            "team_a": team_a,
            "team_b": team_b,
            "snapshots": len(snapshots),
            "first_snapshot": first["timestamp"],
            "latest_snapshot": latest["timestamp"],
            "p_home_change": round(delta_home, 4),
            "p_draw_change": round(delta_draw, 4),
            "p_away_change": round(delta_away, 4),
            "significant_movement": significant,
            "direction": "home" if delta_home > 0.03 else ("away" if delta_away > 0.03 else "stable"),
        }
    
    def get_all_movements(self) -> List[dict]:
        """Get movement analysis for all tracked matches."""
        results = []
        for key in self._history:
            parts = key.split("__")
            if len(parts) == 2:
                movement = self.get_movement(parts[0].title(), parts[1].title())
                if movement:
                    results.append(movement)
        return results


if __name__ == "__main__":
    # Wednesday: python3 odds_client.py [min_liquidity_usd] > data/polymarket_match_odds.json
    min_liq = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    client = PolymarketClient()
    res = client.get_match_1x2_probabilities(min_liquidity=min_liq)
    print(json.dumps(res, indent=2))
