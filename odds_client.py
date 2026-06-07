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

class PolymarketClient:
    """
    Fetches probabilities from Polymarket prediction markets.
    No authentication needed for public market data.
    
    IMPORTANT: Requires User-Agent header or Gamma API returns 403.
    
    Data format notes:
    - Polymarket currently has WC 2026 TOURNAMENT WINNER markets (not match-specific)
    - Tournament winner probabilities can be used to derive relative team strength
    - Match-specific markets typically appear closer to match day
    """
    
    GAMMA_URL = "https://gamma-api.polymarket.com"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    
    def _request(self, endpoint: str, params: dict = None) -> list:
        """Make request to Gamma API with proper headers."""
        if not HAS_URLLIB:
            raise RuntimeError("urllib not available")
        
        url = f"{self.GAMMA_URL}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", self.USER_AGENT)
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            raise RuntimeError(f"Polymarket API error: {e}")
    
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
    
    def get_match_1x2_probabilities(self) -> dict:
        """
        Fetch all active 1X2 match markets from Polymarket and return raw decimal odds.
        Returns a schema ready for the matchday loop:
        { "probabilities": { "Germany|Japan": {"1": 1.45, "X": 4.80, "2": 7.50} } }
        """
        markets = self._request("markets", {
            "limit": 500,
            "active": "true",
            "closed": "false"
        })

        matches = {}
        for m in markets:
            q = m.get("question", "").replace("  ", " ").strip()

            # Filter for match markets (Polymarket typically uses " vs " or " vs. ")
            if " vs " not in q.lower() and " vs. " not in q.lower():
                continue
            # Skip outrights, group winners, or "to advance" props
            if "win the 2026" in q.lower() or "group" in q.lower() or "advance" in q.lower() or "qualify" in q.lower():
                continue

            prices = m.get("outcomePrices", "[]")
            outcomes = m.get("outcomes", "[]")
            if isinstance(prices, str): prices = json.loads(prices)
            if isinstance(outcomes, str): outcomes = json.loads(outcomes)

            if len(prices) >= 2 and len(outcomes) >= 2:
                outcomes_lower = [o.lower() for o in outcomes]

                # Identify a 3-way match market by finding the draw/tie outcome
                draw_idx = -1
                if "draw" in outcomes_lower: draw_idx = outcomes_lower.index("draw")
                elif "tie" in outcomes_lower: draw_idx = outcomes_lower.index("tie")

                if draw_idx == -1:
                    continue

                # Identify the teams (exclude the draw/tie outcome)
                teams = [(i, o) for i, o in enumerate(outcomes) if i != draw_idx]
                if len(teams) >= 2:
                    t1_idx, team_a = teams[0]
                    t2_idx, team_b = teams[1]

                    try:
                        # Polymarket prices are implied probabilities (0-1).
                        p1 = float(prices[t1_idx])
                        p2 = float(prices[t2_idx])
                        px = float(prices[draw_idx])

                        # Convert to decimal odds (protect against zero-division noise)
                        if p1 > 0.005 and p2 > 0.005 and px > 0.005:
                            key = f"{team_a.strip()}|{team_b.strip()}"
                            matches[key] = {
                                "1": round(1.0 / p1, 3),
                                "X": round(1.0 / px, 3),
                                "2": round(1.0 / p2, 3)
                            }
                    except (ValueError, TypeError, IndexError):
                        continue

        return {"source": "polymarket_matches_1x2", "probabilities": matches}


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
    # Wednesday: python3 odds_client.py > data/polymarket_match_odds.json
    client = PolymarketClient()
    res = client.get_match_1x2_probabilities()
    print(json.dumps(res, indent=2))
