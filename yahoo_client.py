"""
Yahoo Fantasy Sports OAuth client and API wrapper.

Handles OAuth 2.0 authentication flow and provides methods to fetch
roster and league configuration from Yahoo Fantasy API.
"""

from __future__ import annotations

import json
import os
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

from config import config


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code: Optional[str] = None

    def do_GET(self) -> None:
        """Handle GET request with OAuth code."""
        # Parse the code from callback URL
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

        # Load existing tokens if available
        self._load_tokens()

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
        """Perform OAuth authorization flow."""
        config.validate()  # Ensure config is present

        if self._is_token_valid():
            print("✓ Using existing valid token")
            return

        if self.refresh_token:
            print("Refreshing access token...")
            if self._refresh_access_token():
                print("✓ Token refreshed successfully")
                return

        # Full authorization flow
        print("\nStarting OAuth authorization flow...")
        print("A browser window will open. Please authorize the application.\n")

        # Build authorization URL
        auth_url = (
            f"{self.OAUTH_BASE}/request_auth"
            f"?client_id={config.client_id}"
            f"&redirect_uri=http://localhost:8000"
            f"&response_type=code"
            f"&language=en-us"
        )

        # Start local server to receive callback
        server = HTTPServer(("localhost", 8000), OAuthCallbackHandler)
        OAuthCallbackHandler.auth_code = None

        # Open browser
        webbrowser.open(auth_url)

        print("Waiting for authorization...")
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
        """Exchange authorization code for access/refresh tokens."""
        config.validate()

        token_url = f"{self.OAUTH_BASE}/get_token"
        data = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": "http://localhost:8000",
            "code": code,
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
        """Refresh access token using refresh token."""
        if not self.refresh_token:
            return False

        config.validate()

        token_url = f"{self.OAUTH_BASE}/get_token"
        data = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": "http://localhost:8000",
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

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def fetch_team_roster(self, league_id: Optional[str] = None, team_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch team roster from Yahoo Fantasy API.

        Args:
            league_id: League ID (defaults to config.league_id)
            team_id: Team ID (defaults to config.team_id)

        Returns:
            List of player dictionaries with name, team, and positions
        """
        league_id = league_id or config.league_id
        team_id = team_id or config.team_id

        if not league_id or not team_id:
            raise ValueError("League ID and Team ID must be provided")

        # Fetch team roster
        endpoint = f"league/nhl.l.{league_id}/teams;team_keys=nhl.l.{league_id}.t.{team_id}/roster"

        data = self._api_request(endpoint)

        # Parse response
        try:
            fantasy_content = data["fantasy_content"]
            league = fantasy_content["league"][0]
            teams = league["teams"]
            team = teams["0"]["team"][1]
            roster = team["roster"]["0"]["players"]

            players = []
            for key, player_data in roster.items():
                if key == "count":
                    continue

                player = player_data["player"][0]
                name_obj = next((p for p in player if isinstance(p, dict) and "name" in p), None)
                team_obj = next((p for p in player if isinstance(p, dict) and "editorial_team_abbr" in p), None)
                pos_obj = next((p for p in player if isinstance(p, dict) and "eligible_positions" in p), None)

                if name_obj and team_obj and pos_obj:
                    full_name = name_obj["name"]["full"]
                    team_abbr = team_obj["editorial_team_abbr"]
                    positions = [p["position"] for p in pos_obj["eligible_positions"]]

                    # Filter out utility positions and bench
                    positions = [p for p in positions if p not in ("Util", "BN", "IR", "IR+", "NA")]

                    players.append({
                        "name": full_name,
                        "team": team_abbr,
                        "pos": positions,
                    })

            return players

        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Failed to parse roster data: {e}")

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
            league = fantasy_content["league"][0]
            settings = league["settings"][0]
            roster_positions = settings["roster_positions"]

            # Parse roster slots
            slots = []
            for key, pos_data in roster_positions.items():
                if key == "count":
                    continue

                pos = pos_data["roster_position"]
                position_type = pos["position"]
                count = int(pos.get("count", 1))

                # Skip bench, IR, and utility slots for bodies table
                if position_type not in ("BN", "IR", "IR+", "Util", "NA"):
                    slots.extend([position_type] * count)

            return {
                "slots": slots,
                "league_name": league.get("name", ""),
            }

        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Failed to parse league settings: {e}")
