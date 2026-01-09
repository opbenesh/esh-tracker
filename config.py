"""
Configuration management for Spotify Release Tracker.

Provides centralized configuration with environment variable support.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class TrackerConfig:
    """Configuration for Spotify Release Tracker."""

    # API Settings
    client_id: str
    client_secret: str
    market: str = 'IL'

    # Tracking Settings
    lookback_days: int = 90
    noise_keywords: List[str] = field(default_factory=lambda: [
        'live', 'remaster', 'demo', 'commentary',
        'instrumental', 'karaoke'
    ])

    # Performance Settings
    max_workers: int = 8
    api_retry_attempts: int = 3
    retry_base_delay: float = 2.0

    # Database Settings
    db_path: str = 'artists.db'

    # Logging Settings
    log_level: str = 'INFO'
    log_file: str = 'app.log'

    @classmethod
    def from_env(cls) -> 'TrackerConfig':
        """
        Load configuration from environment variables.

        Returns:
            TrackerConfig instance with values from environment

        Raises:
            ValueError: If required environment variables are missing
        """
        client_id = os.getenv('SPOTIPY_CLIENT_ID')
        client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError(
                "Missing required environment variables: "
                "SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET"
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            market=os.getenv('SPOTIFY_MARKET', 'IL'),
            lookback_days=int(os.getenv('LOOKBACK_DAYS', '90')),
            max_workers=int(os.getenv('MAX_WORKERS', '8')),
            api_retry_attempts=int(os.getenv('API_RETRY_ATTEMPTS', '3')),
            retry_base_delay=float(os.getenv('RETRY_BASE_DELAY', '2.0')),
            db_path=os.getenv('DB_PATH', 'artists.db'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            log_file=os.getenv('LOG_FILE', 'app.log')
        )

    def validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If configuration values are invalid
        """
        if self.lookback_days < 1:
            raise ValueError("lookback_days must be positive")

        if self.max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        if self.api_retry_attempts < 0:
            raise ValueError("api_retry_attempts cannot be negative")

        if self.retry_base_delay <= 0:
            raise ValueError("retry_base_delay must be positive")

        if not self.client_id or not self.client_secret:
            raise ValueError("client_id and client_secret are required")
