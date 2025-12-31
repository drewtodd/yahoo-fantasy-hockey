"""
Configuration management for Yahoo Fantasy Hockey integration.

Loads credentials from environment variables or .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def load_env_file(env_path: str = ".env") -> None:
    """Load environment variables from .env file if it exists."""
    env_file = Path(env_path)
    if not env_file.exists():
        return

    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


# Load .env file on module import
load_env_file()


class Config:
    """Yahoo Fantasy API configuration."""

    def __init__(self) -> None:
        self.client_id: Optional[str] = os.getenv("YAHOO_CLIENT_ID")
        self.client_secret: Optional[str] = os.getenv("YAHOO_CLIENT_SECRET")
        self.league_id: Optional[str] = os.getenv("YAHOO_LEAGUE_ID")
        self.team_id: Optional[str] = os.getenv("YAHOO_TEAM_ID")
        self.token_file: str = os.getenv("YAHOO_TOKEN_FILE", ".yahoo_tokens.json")

    def validate(self) -> None:
        """Validate that all required configuration is present.

        Note: YAHOO_CLIENT_SECRET is optional for Public Client OAuth apps.
        """
        missing = []
        if not self.client_id:
            missing.append("YAHOO_CLIENT_ID")
        # client_secret is optional for Public Client OAuth
        if not self.league_id:
            missing.append("YAHOO_LEAGUE_ID")
        if not self.team_id:
            missing.append("YAHOO_TEAM_ID")

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Please set them in .env file or environment."
            )

    @property
    def is_configured(self) -> bool:
        """Check if all required config is present.

        Note: client_secret is optional for Public Client OAuth.
        """
        return bool(self.client_id and self.league_id and self.team_id)


# Global config instance
config = Config()
