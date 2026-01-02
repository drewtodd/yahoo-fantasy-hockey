"""
Yahoo Fantasy Sports OAuth client and API wrapper.

Handles OAuth 2.0 authentication flow and provides methods to fetch
roster and league configuration from Yahoo Fantasy API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import ssl
import subprocess
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from config import config

# Cache configuration
_cache_dir = Path(".cache")
_yahoo_fa_cache_file = _cache_dir / "yahoo_free_agents.json"
_cache_ttl = 3600  # 1 hour cache for Yahoo free agents (stats update frequently during games)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code: Optional[str] = None

    def do_GET(self) -> None:
        """Handle GET request with OAuth code."""
        query = urlparse(self.path).query
        params = parse_qs(query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this window and return to the terminal.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization failed</h1></body></html>")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress log messages."""
        pass




class YahooClient:
    """Yahoo Fantasy Sports API client with OAuth 2.0 support."""

    OAUTH_BASE = "https://api.login.yahoo.com/oauth2"
    API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

    def __init__(self, token_file: Optional[str] = None) -> None:
        """Initialize Yahoo client.

        Args:
            token_file: Path to token storage file. Defaults to config.token_file
        """
        self.token_file = token_file or config.token_file
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[float] = None
        self.code_verifier: Optional[str] = None  # For PKCE

        # Load existing tokens if available
        self._load_tokens()

    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge for Public Client flow."""
        # Generate random code verifier
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

        # Generate code challenge (SHA256 hash of verifier)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')

        return code_verifier, code_challenge

    def _ensure_ssl_cert(self) -> tuple[str, str]:
        """Generate self-signed SSL certificate for localhost if it doesn't exist."""
        cert_file = ".yahoo_cert.pem"
        key_file = ".yahoo_key.pem"

        if Path(cert_file).exists() and Path(key_file).exists():
            return cert_file, key_file

        # Generate self-signed certificate using openssl
        print("Generating self-signed SSL certificate for localhost...")
        try:
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:4096",
                "-keyout", key_file, "-out", cert_file,
                "-days", "365", "-nodes",
                "-subj", "/CN=localhost"
            ], check=True, capture_output=True)

            # Set restrictive permissions
            os.chmod(cert_file, 0o600)
            os.chmod(key_file, 0o600)

            print("✓ SSL certificate generated")
            return cert_file, key_file
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to generate SSL certificate: {e.stderr.decode()}")

    def _load_tokens(self) -> None:
        """Load OAuth tokens from file."""
        if not Path(self.token_file).exists():
            return

        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                tokens = json.load(f)
                self.access_token = tokens.get("access_token")
                self.refresh_token = tokens.get("refresh_token")
                self.token_expiry = tokens.get("expiry")
        except (json.JSONDecodeError, IOError):
            pass

    def _save_tokens(self) -> None:
        """Save OAuth tokens to file with restricted permissions."""
        tokens = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expiry": self.token_expiry,
        }

        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)

        # Set file permissions to user-only (0600)
        os.chmod(self.token_file, 0o600)

    def _is_token_valid(self) -> bool:
        """Check if current access token is valid."""
        if not self.access_token or not self.token_expiry:
            return False
        # Add 60 second buffer
        return time.time() < (self.token_expiry - 60)

    def authorize(self) -> None:
        """Perform OAuth authorization flow with PKCE for Public Client."""
        config.validate()  # Ensure config is present

        if self._is_token_valid():
            print("✓ Using existing valid token")
            return

        if self.refresh_token:
            print("Refreshing access token...")
            if self._refresh_access_token():
                print("✓ Token refreshed successfully")
                return

        # Full authorization flow with PKCE (required for Yahoo Public Client)
        print("\nStarting OAuth authorization flow...")
        print("A browser window will open. Please authorize the application.\n")

        # Generate PKCE pair
        self.code_verifier, code_challenge = self._generate_pkce_pair()

        # Ensure SSL certificate exists
        cert_file, key_file = self._ensure_ssl_cert()

        # Build authorization URL with PKCE (HTTPS required by Yahoo)
        auth_url = (
            f"{self.OAUTH_BASE}/request_auth"
            f"?client_id={config.client_id}"
            f"&redirect_uri=https://localhost:8000"
            f"&response_type=code"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
            f"&language=en-us"
        )

        # Start HTTPS server to receive callback
        server = HTTPServer(("localhost", 8000), OAuthCallbackHandler)
        OAuthCallbackHandler.auth_code = None

        # Wrap with SSL
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        server.socket = context.wrap_socket(server.socket, server_side=True)

        # Open browser
        webbrowser.open(auth_url)

        print("Waiting for authorization...")
        print("(You may see a browser warning about the self-signed certificate - this is normal)")
        print("Click 'Advanced' and 'Proceed to localhost' to continue\n")

        # Wait for callback (timeout after 5 minutes)
        timeout = time.time() + 300
        while OAuthCallbackHandler.auth_code is None and time.time() < timeout:
            server.handle_request()

        if OAuthCallbackHandler.auth_code is None:
            raise RuntimeError("Authorization timed out or failed")

        # Exchange code for tokens
        self._exchange_code_for_token(OAuthCallbackHandler.auth_code)
        print("✓ Authorization successful")

    def _exchange_code_for_token(self, code: str) -> None:
        """Exchange authorization code for access/refresh tokens using PKCE."""
        config.validate()

        token_url = f"{self.OAUTH_BASE}/get_token"
        data = {
            "client_id": config.client_id,
            "redirect_uri": "https://localhost:8000",
            "code": code,
            "code_verifier": self.code_verifier,  # PKCE verifier
            "grant_type": "authorization_code",
        }

        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()

        tokens = response.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]
        self.token_expiry = time.time() + tokens["expires_in"]

        self._save_tokens()

    def _refresh_access_token(self) -> bool:
        """Refresh access token using refresh token (Public Client - no secret needed)."""
        if not self.refresh_token:
            return False

        config.validate()

        token_url = f"{self.OAUTH_BASE}/get_token"
        data = {
            "client_id": config.client_id,
            "redirect_uri": "https://localhost:8000",
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()

            tokens = response.json()
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens["refresh_token"]
            self.token_expiry = time.time() + tokens["expires_in"]

            self._save_tokens()
            return True
        except requests.RequestException:
            return False

    def _api_request(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Make authenticated API request.

        Args:
            endpoint: API endpoint path
            params: Optional query parameters

        Returns:
            JSON response data
        """
        if not self._is_token_valid():
            self.authorize()

        url = f"{self.API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

        # Ensure we request JSON format (Yahoo defaults to XML)
        if params is None:
            params = {}
        params["format"] = "json"

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        # Parse JSON response
        try:
            return response.json()
        except ValueError as e:
            raise RuntimeError(f"Invalid JSON response from Yahoo API. Check that the endpoint is correct.")

    def fetch_team_roster(self, league_id: Optional[str] = None, team_id: Optional[str] = None, include_stats: bool = False) -> List[Dict[str, Any]]:
        """Fetch team roster from Yahoo Fantasy API.

        Args:
            league_id: League ID (defaults to config.league_id)
            team_id: Team ID (defaults to config.team_id)
            include_stats: Include player stats and fantasy points (default False)

        Returns:
            List of player dictionaries with name, team, and positions
            If include_stats=True, also includes fantasy_points_total
        """
        league_id = league_id or config.league_id
        team_id = team_id or config.team_id

        if not league_id or not team_id:
            raise ValueError("League ID and Team ID must be provided")

        # Fetch team roster (with stats if requested)
        if include_stats:
            endpoint = f"team/nhl.l.{league_id}.t.{team_id}/roster/players/stats"
        else:
            endpoint = f"league/nhl.l.{league_id}/teams;team_keys=nhl.l.{league_id}.t.{team_id}/roster"

        data = self._api_request(endpoint)

        # Parse response
        try:
            fantasy_content = data["fantasy_content"]

            # Different parsing for stats vs no-stats endpoints
            if include_stats:
                # stats endpoint returns team directly
                team_data = fantasy_content["team"]
                if isinstance(team_data, list):
                    team_data = team_data[0]

                # Find roster in team data
                roster_data = None
                for item in team_data:
                    if isinstance(item, dict) and "roster" in item:
                        roster_data = item["roster"]
                        break

                if not roster_data:
                    raise RuntimeError("No roster data found in team response")

                # roster_data is a list, get first element
                if isinstance(roster_data, list):
                    roster_dict = roster_data[0]
                else:
                    roster_dict = roster_data

                players_data = roster_dict.get("players", {})
            else:
                # Original no-stats parsing
                league_teams = fantasy_content["league"][1]
                teams = league_teams["teams"]
                team = teams["0"]["team"]

                # Find the roster data in the team array
                roster_data = None
                for item in team:
                    if isinstance(item, list):
                        roster_data = item[0].get("roster") if item else None
                        if roster_data:
                            break
                    elif isinstance(item, dict) and "roster" in item:
                        roster_data = item["roster"]
                        break

                if not roster_data:
                    raise RuntimeError("No roster data found in team response")

                # roster_data is a list, get first element
                if isinstance(roster_data, list):
                    roster_dict = roster_data[0]
                else:
                    roster_dict = roster_data.get("0", {})

                players_data = roster_dict.get("players", {})

            players = []
            for key, player_data in players_data.items():
                if key == "count":
                    continue

                player_wrapper = player_data["player"]

                # First element contains player attributes
                player = player_wrapper[0]
                name_obj = next((p for p in player if isinstance(p, dict) and "name" in p), None)
                team_obj = next((p for p in player if isinstance(p, dict) and "editorial_team_abbr" in p), None)
                pos_obj = next((p for p in player if isinstance(p, dict) and "eligible_positions" in p), None)

                if name_obj and team_obj and pos_obj:
                    full_name = name_obj["name"]["full"]
                    team_abbr = team_obj["editorial_team_abbr"]
                    positions = [p["position"] for p in pos_obj["eligible_positions"]]

                    # Filter out utility positions and bench
                    positions = [p for p in positions if p not in ("Util", "BN", "IR", "IR+", "NA")]

                    player_dict = {
                        "name": full_name,
                        "team": team_abbr,
                        "pos": positions,
                    }

                    # Extract fantasy points if stats were requested
                    if include_stats and len(player_wrapper) > 1:
                        for elem in player_wrapper[1:]:
                            if isinstance(elem, dict) and "player_points" in elem:
                                player_points = elem["player_points"]
                                if "total" in player_points:
                                    try:
                                        player_dict["fantasy_points_total"] = float(player_points["total"])
                                    except (ValueError, TypeError):
                                        player_dict["fantasy_points_total"] = 0.0
                                break

                    players.append(player_dict)

            return players

        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise RuntimeError(f"Failed to parse roster data from Yahoo API: {e}")

    def fetch_league_settings(self, league_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch league roster settings.

        Args:
            league_id: League ID (defaults to config.league_id)

        Returns:
            Dictionary with roster position configuration
        """
        league_id = league_id or config.league_id

        if not league_id:
            raise ValueError("League ID must be provided")

        endpoint = f"league/nhl.l.{league_id}/settings"
        data = self._api_request(endpoint)

        try:
            fantasy_content = data["fantasy_content"]
            # League metadata is in index 0, settings are in index 1
            league_info = fantasy_content["league"][0]
            league_settings = fantasy_content["league"][1]
            settings = league_settings["settings"][0]
            roster_positions = settings["roster_positions"]

            # Parse roster slots
            slots = []
            # roster_positions is a list of dicts
            for pos_data in roster_positions:
                pos = pos_data["roster_position"]
                position_type = pos["position"]
                count = int(pos.get("count", 1))

                # Skip bench, IR, and utility slots for bodies table
                if position_type not in ("BN", "IR", "IR+", "Util", "NA"):
                    slots.extend([position_type] * count)

            return {
                "slots": slots,
                "league_name": league_info.get("name", ""),
            }

        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Failed to parse league settings from Yahoo API: {e}")

    def fetch_player_details(self, player_id: str, league_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch player details by Yahoo player ID.

        Args:
            player_id: Yahoo player ID (e.g., "5479")
            league_id: League ID (defaults to config.league_id)

        Returns:
            Dictionary with player name, team, and positions
        """
        league_id = league_id or config.league_id

        if not league_id:
            raise ValueError("League ID must be provided")

        # Yahoo player key format: nhl.p.{player_id}
        endpoint = f"league/nhl.l.{league_id}/players;player_keys=nhl.p.{player_id}"

        data = self._api_request(endpoint)

        try:
            fantasy_content = data["fantasy_content"]
            league = fantasy_content["league"]

            # Find players data in league array
            players_data = None
            for item in league:
                if isinstance(item, dict) and "players" in item:
                    players_data = item["players"]
                    break

            if not players_data:
                raise RuntimeError(f"Player {player_id} not found in league")

            # Get first player (should be only one)
            player_data = players_data["0"]["player"][0]

            name_obj = next((p for p in player_data if isinstance(p, dict) and "name" in p), None)
            team_obj = next((p for p in player_data if isinstance(p, dict) and "editorial_team_abbr" in p), None)
            pos_obj = next((p for p in player_data if isinstance(p, dict) and "eligible_positions" in p), None)

            if not (name_obj and team_obj and pos_obj):
                raise RuntimeError(f"Incomplete player data for player {player_id}")

            full_name = name_obj["name"]["full"]
            team_abbr = team_obj["editorial_team_abbr"]
            positions = [p["position"] for p in pos_obj["eligible_positions"]]

            # Filter out utility positions and bench
            positions = [p for p in positions if p not in ("Util", "BN", "IR", "IR+", "NA")]

            return {
                "name": full_name,
                "team": team_abbr,
                "pos": positions,
            }

        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise RuntimeError(f"Failed to fetch player {player_id} from Yahoo API: {e}")

    def _load_fa_cache(self, league_id: str) -> Optional[List[Dict[str, Any]]]:
        """Load free agents cache from disk if fresh."""
        if not _yahoo_fa_cache_file.exists():
            return None

        try:
            # Check file modification time
            file_mtime = os.path.getmtime(_yahoo_fa_cache_file)
            current_time = time.time()
            age = current_time - file_mtime

            # If cache is older than TTL, don't use it
            if age > _cache_ttl:
                return None

            # Load cache from file
            with open(_yahoo_fa_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Verify league ID matches
            if cache_data.get("league_id") != league_id:
                return None

            print(f"  ✓ Loaded free agents from cache ({age / 60:.1f} minutes old)")
            return cache_data.get("players", [])

        except Exception:
            return None

    def _save_fa_cache(self, league_id: str, players: List[Dict[str, Any]]) -> None:
        """Save free agents cache to disk."""
        try:
            # Create cache directory if it doesn't exist
            _cache_dir.mkdir(exist_ok=True)

            cache_data = {
                "league_id": league_id,
                "timestamp": time.time(),
                "players": players
            }

            # Save to temp file first, then rename (atomic operation)
            temp_file = _yahoo_fa_cache_file.with_suffix('.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)

            # Atomic rename
            temp_file.replace(_yahoo_fa_cache_file)

        except Exception:
            pass  # Fail silently, cache is optional

    def fetch_available_players(
        self,
        league_id: Optional[str] = None,
        count: int = 100,
        start: int = 0,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch available free agents from Yahoo Fantasy API.

        Args:
            league_id: League ID (defaults to config.league_id)
            count: Number of players to fetch (default 100)
            start: Starting index for pagination (default 0)
            use_cache: Use cached data if available and fresh (default True)

        Returns:
            List of player dictionaries with name, team, positions, player_id,
            ownership percentage, stats, fantasy_points_total, and overall_rank
        """
        league_id = league_id or config.league_id

        if not league_id:
            raise ValueError("League ID must be provided")

        # Check cache if enabled and fetching from start
        if use_cache and start == 0:
            cached_players = self._load_fa_cache(league_id)
            if cached_players:
                # Return subset if count is less than cached
                return cached_players[:count] if count < len(cached_players) else cached_players

        # Fetch free agents sorted by overall rank with stats, ownership, and ranks
        endpoint = (
            f"league/nhl.l.{league_id}/players;"
            f"status=FA;"
            f"sort=OR;"
            f"count={count};"
            f"start={start};"
            f"out=percent_owned,stats,ranks"
        )

        data = self._api_request(endpoint)

        try:
            fantasy_content = data["fantasy_content"]
            league = fantasy_content["league"]

            # Find players data in league array
            players_data = None
            for item in league:
                if isinstance(item, dict) and "players" in item:
                    players_data = item["players"]
                    break

            if not players_data:
                return []

            players = []
            # Get player count
            count_val = players_data.get("count", 0)

            for i in range(count_val):
                key = str(i)
                if key not in players_data:
                    continue

                player_wrapper = players_data[key]["player"]

                # player_wrapper is an array with 4 elements:
                # [0] = array of player attribute objects
                # [1] = percent_owned object
                # [2] = player_stats/player_points object
                # [3] = player_ranks object (when ranks requested)

                player_id = None
                name = None
                team_abbr = None
                positions = []
                ownership_pct = 0.0
                stats_dict = {}
                overall_rank = None
                is_injured = False
                injury_status = None

                # Parse player attributes from first array element
                if len(player_wrapper) > 0 and isinstance(player_wrapper[0], list):
                    for item in player_wrapper[0]:
                        if not isinstance(item, dict):
                            continue

                        # Extract player ID
                        if "player_id" in item:
                            player_id = item["player_id"]

                        # Extract name
                        if "name" in item:
                            name = item["name"]["full"]

                        # Extract team
                        if "editorial_team_abbr" in item:
                            team_abbr = item["editorial_team_abbr"]

                        # Extract injury status
                        if "status" in item:
                            injury_status = item.get("status")
                            if injury_status in ("IR", "O", "D"):  # IR, Out, Day-to-Day
                                is_injured = True

                        # Extract positions
                        if "eligible_positions" in item:
                            positions = [p["position"] for p in item["eligible_positions"]]
                            # Filter out utility positions
                            positions = [p for p in positions if p not in ("Util", "BN", "IR", "IR+", "NA")]

                # Parse ownership from second array element
                if len(player_wrapper) > 1 and isinstance(player_wrapper[1], dict):
                    pct_data = player_wrapper[1].get("percent_owned", [])
                    if isinstance(pct_data, list):
                        # Find the value object in the array
                        for pct_obj in pct_data:
                            if isinstance(pct_obj, dict) and "value" in pct_obj:
                                ownership_pct = float(pct_obj["value"])
                                break

                # Parse stats and fantasy points from third array element
                fantasy_points_total = 0.0
                if len(player_wrapper) > 2 and isinstance(player_wrapper[2], dict):
                    # Extract individual stats
                    player_stats = player_wrapper[2].get("player_stats", {})
                    if "stats" in player_stats:
                        stats_list = player_stats["stats"]
                        # Parse stats into dictionary
                        for stat in stats_list:
                            if "stat" in stat:
                                stat_obj = stat["stat"]
                                stat_id = stat_obj.get("stat_id")
                                value = stat_obj.get("value")
                                if stat_id and value:
                                    stats_dict[stat_id] = value

                    # Extract total fantasy points (provided directly by Yahoo)
                    player_points = player_wrapper[2].get("player_points", {})
                    if "total" in player_points:
                        try:
                            fantasy_points_total = float(player_points["total"])
                        except (ValueError, TypeError):
                            fantasy_points_total = 0.0

                # Parse ranks from fourth array element
                if len(player_wrapper) > 3 and isinstance(player_wrapper[3], dict):
                    player_ranks = player_wrapper[3].get("player_ranks", [])
                    # Find the current season rank (S/2025) instead of preseason OR rank
                    for rank_entry in player_ranks:
                        if isinstance(rank_entry, dict) and "player_rank" in rank_entry:
                            rank_obj = rank_entry["player_rank"]
                            # Use current season rank (S with season 2025) for accurate current performance
                            if rank_obj.get("rank_type") == "S" and rank_obj.get("rank_season") == "2025":
                                try:
                                    overall_rank = int(rank_obj.get("rank_value", 0))
                                except (ValueError, TypeError):
                                    overall_rank = None
                                break
                    # Fallback to OR (preseason rank) if no current season rank found
                    if overall_rank is None:
                        for rank_entry in player_ranks:
                            if isinstance(rank_entry, dict) and "player_rank" in rank_entry:
                                rank_obj = rank_entry["player_rank"]
                                if rank_obj.get("rank_type") == "OR":
                                    try:
                                        overall_rank = int(rank_obj.get("rank_value", 0))
                                    except (ValueError, TypeError):
                                        overall_rank = None
                                    break

                if player_id and name and team_abbr:
                    players.append({
                        "player_id": player_id,
                        "name": name,
                        "team": team_abbr,
                        "pos": positions,
                        "ownership_pct": ownership_pct,
                        "stats": stats_dict,
                        "fantasy_points_total": fantasy_points_total,
                        "overall_rank": overall_rank,
                        "is_injured": is_injured,
                        "injury_status": injury_status
                    })

            # Save to cache if fetching from start (full list)
            if start == 0:
                self._save_fa_cache(league_id, players)

            return players

        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise RuntimeError(f"Failed to fetch available players from Yahoo API: {e}")
