#!/usr/bin/env python3
"""
Artist Database Module

Manages SQLite database for storing tracked artists.
"""

import json
import re
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple
import logging

from .exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)


class ArtistDatabase:
    """Manages artist storage in SQLite database."""

    # Spotify artist ID is base62 encoded, 22 characters
    SPOTIFY_ID_PATTERN = re.compile(r'^[a-zA-Z0-9]{22}$')

    def __init__(self, db_path: str = 'artists.db'):
        """
        Initialize the artist database.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    @staticmethod
    def _validate_artist_name(artist_name: str) -> None:
        """
        Validate artist name.

        Args:
            artist_name: Name to validate

        Raises:
            ValidationError: If validation fails
        """
        if not artist_name:
            raise ValidationError('artist_name', artist_name, 'Artist name cannot be empty')

        if not artist_name.strip():
            raise ValidationError('artist_name', artist_name, 'Artist name cannot be only whitespace')

        if len(artist_name) > 500:
            raise ValidationError('artist_name', artist_name[:50] + '...',
                                'Artist name is too long (max 500 characters)')

    @staticmethod
    def _validate_spotify_id(spotify_artist_id: str) -> None:
        """
        Validate Spotify artist ID.

        Args:
            spotify_artist_id: Spotify ID to validate

        Raises:
            ValidationError: If validation fails
        """
        if not spotify_artist_id:
            raise ValidationError('spotify_artist_id', spotify_artist_id, 'Spotify ID cannot be empty')

        if not spotify_artist_id.strip():
            raise ValidationError('spotify_artist_id', spotify_artist_id, 'Spotify ID cannot be only whitespace')

        if not ArtistDatabase.SPOTIFY_ID_PATTERN.match(spotify_artist_id):
            raise ValidationError('spotify_artist_id', spotify_artist_id,
                                'Spotify ID must be exactly 22 alphanumeric characters')

    def _init_database(self) -> None:
        """Create the database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_added TEXT NOT NULL,
                    artist_name TEXT NOT NULL,
                    spotify_artist_id TEXT NOT NULL UNIQUE
                )
            ''')

            # Create index on spotify_artist_id for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_spotify_artist_id
                ON artists(spotify_artist_id)
            ''')

            # Create releases cache table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS releases_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_id TEXT NOT NULL,
                    album_id TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    isrc TEXT,
                    release_date TEXT NOT NULL,
                    album_name TEXT NOT NULL,
                    track_name TEXT NOT NULL,
                    album_type TEXT NOT NULL,
                    popularity INTEGER,
                    spotify_url TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    UNIQUE(track_id)
                )
            ''')

            # Create indexes for faster cache lookups
            # Composite index for optimal cache query performance
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_releases_artist_date_fetch
                ON releases_cache(artist_id, release_date, fetched_at)
            ''')

            # Legacy indexes (kept for backwards compatibility)
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_releases_artist_date
                ON releases_cache(artist_id, release_date)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_releases_fetched
                ON releases_cache(fetched_at)
            ''')

            # Index for track_id lookups (used in deduplication)
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_releases_track_id
                ON releases_cache(track_id)
            ''')

            # Create ISRC lookup cache table (immutable, no expiry)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS isrc_lookup_cache (
                    isrc TEXT PRIMARY KEY,
                    earliest_date TEXT NOT NULL,
                    earliest_album_name TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                )
            ''')

            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    def add_artist(
        self,
        artist_name: str,
        spotify_artist_id: str
    ) -> bool:
        """
        Add an artist to the database.

        Args:
            artist_name: Name of the artist
            spotify_artist_id: Spotify artist ID

        Returns:
            True if artist was added, False if already exists

        Raises:
            ValidationError: If inputs are invalid
            DatabaseError: If database operation fails
        """
        # Validate inputs
        self._validate_artist_name(artist_name)
        self._validate_spotify_id(spotify_artist_id)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                date_added = datetime.now().isoformat()

                cursor.execute('''
                    INSERT INTO artists (date_added, artist_name, spotify_artist_id)
                    VALUES (?, ?, ?)
                ''', (date_added, artist_name, spotify_artist_id))

                conn.commit()
                logger.info(f"Added artist '{artist_name}' (ID: {spotify_artist_id})")
                return True

        except sqlite3.IntegrityError:
            logger.debug(f"Artist '{artist_name}' already exists in database")
            return False
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to add artist: {e}") from e

    def add_artists_batch(
        self,
        artists: List[Tuple[str, str]]
    ) -> Tuple[int, int]:
        """
        Add multiple artists to the database.

        Args:
            artists: List of tuples (artist_name, spotify_artist_id)

        Returns:
            Tuple of (added_count, skipped_count)
        """
        added = 0
        skipped = 0

        for artist_name, spotify_artist_id in artists:
            if self.add_artist(artist_name, spotify_artist_id):
                added += 1
            else:
                skipped += 1

        return added, skipped

    def get_all_artists(self) -> List[Tuple[str, str, str, str]]:
        """
        Get all artists from the database.

        Returns:
            List of tuples (id, date_added, artist_name, spotify_artist_id)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, date_added, artist_name, spotify_artist_id
                FROM artists
                ORDER BY date_added DESC
            ''')
            return cursor.fetchall()

    def get_artist_ids(self) -> List[str]:
        """
        Get all Spotify artist IDs from the database.

        Returns:
            List of Spotify artist IDs
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT spotify_artist_id FROM artists')
            return [row[0] for row in cursor.fetchall()]

    def get_artist_by_id(self, spotify_artist_id: str) -> Optional[Tuple[str, str, str, str]]:
        """
        Get an artist by Spotify ID.

        Args:
            spotify_artist_id: Spotify artist ID

        Returns:
            Tuple of (id, date_added, artist_name, spotify_artist_id) or None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, date_added, artist_name, spotify_artist_id
                FROM artists
                WHERE spotify_artist_id = ?
            ''', (spotify_artist_id,))
            return cursor.fetchone()

    def remove_artist(self, spotify_artist_id: str) -> bool:
        """
        Remove an artist from the database.

        Args:
            spotify_artist_id: Spotify artist ID

        Returns:
            True if artist was removed, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM artists
                WHERE spotify_artist_id = ?
            ''', (spotify_artist_id,))
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Removed artist with ID: {spotify_artist_id}")
                return True
            else:
                logger.warning(f"Artist with ID {spotify_artist_id} not found")
                return False

    def get_artist_count(self) -> int:
        """
        Get the total number of tracked artists.

        Returns:
            Number of artists in the database
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM artists')
            return cursor.fetchone()[0]

    def clear_all_artists(self) -> int:
        """
        Remove all artists from the database.

        Returns:
            Number of artists removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM artists')
            count = cursor.fetchone()[0]

            cursor.execute('DELETE FROM artists')
            conn.commit()

            logger.info(f"Cleared {count} artists from database")
            return count

    def export_to_json(self, filepath: str) -> int:
        """
        Export database to JSON for backup.

        Args:
            filepath: Path to output JSON file

        Returns:
            Number of artists exported

        Raises:
            DatabaseError: If export fails
        """
        try:
            artists = self.get_all_artists()
            data = [
                {
                    'date_added': artist[1],
                    'artist_name': artist[2],
                    'spotify_artist_id': artist[3]
                }
                for artist in artists
            ]

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Exported {len(data)} artists to {filepath}")
            return len(data)

        except Exception as e:
            raise DatabaseError(f"Failed to export to JSON: {e}") from e

    def import_from_json(self, filepath: str) -> Tuple[int, int]:
        """
        Import artists from JSON backup.

        Args:
            filepath: Path to input JSON file

        Returns:
            Tuple of (added_count, skipped_count)

        Raises:
            DatabaseError: If import fails
            ValidationError: If JSON data is invalid
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValidationError('json_data', type(data).__name__,
                                    'JSON must contain an array of artists')

            artists = []
            for item in data:
                if not isinstance(item, dict):
                    logger.warning(f"Skipping invalid item: {item}")
                    continue

                artist_name = item.get('artist_name')
                spotify_id = item.get('spotify_artist_id')

                if not artist_name or not spotify_id:
                    logger.warning(f"Skipping incomplete item: {item}")
                    continue

                artists.append((artist_name, spotify_id))

            added, skipped = self.add_artists_batch(artists)
            logger.info(f"Imported from {filepath}: {added} added, {skipped} skipped")
            return added, skipped

        except FileNotFoundError:
            raise DatabaseError(f"File not found: {filepath}")
        except json.JSONDecodeError as e:
            raise DatabaseError(f"Invalid JSON file: {e}") from e
        except Exception as e:
            raise DatabaseError(f"Failed to import from JSON: {e}") from e

    def cache_release(self, release_data: dict) -> bool:
        """
        Cache a release in the database.

        Args:
            release_data: Dictionary with release information

        Returns:
            True if cached successfully, False if already exists

        Raises:
            DatabaseError: If caching fails
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                fetched_at = datetime.now().isoformat()

                cursor.execute('''
                    INSERT OR REPLACE INTO releases_cache
                    (artist_id, album_id, track_id, isrc, release_date, album_name,
                     track_name, album_type, popularity, spotify_url, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    release_data.get('artist_id'),
                    release_data.get('album_id'),
                    release_data.get('track_id'),
                    release_data.get('isrc'),
                    release_data.get('release_date'),
                    release_data.get('album_name'),
                    release_data.get('track_name'),
                    release_data.get('album_type'),
                    release_data.get('popularity'),
                    release_data.get('spotify_url'),
                    fetched_at
                ))

                conn.commit()
                return True

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to cache release: {e}") from e

    def _calculate_adaptive_ttl(self, artist_id: str) -> int:
        """
        Calculate adaptive cache TTL based on artist activity.

        Active artists (recent releases): 6 hours
        Moderate activity: 24 hours
        Inactive (no recent releases): 7 days (168 hours)

        Args:
            artist_id: Spotify artist ID

        Returns:
            Cache TTL in hours
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get the most recent release date for this artist
                cursor.execute('''
                    SELECT MAX(release_date) FROM releases_cache
                    WHERE artist_id = ?
                ''', (artist_id,))

                result = cursor.fetchone()
                if not result or not result[0]:
                    return 24  # Default to 24 hours if no data

                last_release_str = result[0]
                last_release_date = datetime.fromisoformat(last_release_str) if 'T' not in last_release_str else datetime.strptime(last_release_str, '%Y-%m-%d')

                days_since_release = (datetime.now() - last_release_date).days

                # Adaptive TTL based on activity
                if days_since_release < 30:
                    return 6  # Active: check frequently
                elif days_since_release < 180:
                    return 24  # Moderate: standard check
                else:
                    return 168  # Inactive: cache longer (7 days)

        except Exception as e:
            logger.warning(f"Error calculating adaptive TTL for artist {artist_id}: {e}")
            return 24  # Default fallback

    def get_cached_releases(self, artist_id: str, cutoff_date: str, max_age_hours: Optional[int] = None) -> List[dict]:
        """
        Get cached releases for an artist within the date range, if cache is fresh.

        Args:
            artist_id: Spotify artist ID
            cutoff_date: Minimum release date to consider (YYYY-MM-DD)
            max_age_hours: Maximum age of cache in hours (default: None, uses adaptive TTL)

        Returns:
            List of cached release dictionaries, or empty list if cache is stale
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Use adaptive TTL if not specified
                if max_age_hours is None:
                    max_age_hours = self._calculate_adaptive_ttl(artist_id)
                    logger.debug(f"Using adaptive TTL of {max_age_hours}h for artist {artist_id}")

                # Calculate cache expiry time
                from datetime import timedelta
                cache_expiry = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

                cursor.execute('''
                    SELECT artist_id, album_id, track_id, isrc, release_date, album_name,
                           track_name, album_type, popularity, spotify_url, fetched_at
                    FROM releases_cache
                    WHERE artist_id = ?
                    AND release_date >= ?
                    AND fetched_at >= ?
                    ORDER BY release_date DESC
                ''', (artist_id, cutoff_date, cache_expiry))

                rows = cursor.fetchall()
                releases = []

                for row in rows:
                    releases.append({
                        'artist_id': row[0],
                        'album_id': row[1],
                        'track_id': row[2],
                        'isrc': row[3],
                        'release_date': row[4],
                        'album_name': row[5],
                        'track_name': row[6],
                        'album_type': row[7],
                        'popularity': row[8],
                        'spotify_url': row[9],
                        'fetched_at': row[10]
                    })

                return releases

        except sqlite3.Error as e:
            logger.error(f"Error fetching cached releases: {e}")
            return []

    def clear_expired_cache(self, max_age_hours: int = 168) -> int:
        """
        Clear cache entries older than specified hours.

        Args:
            max_age_hours: Maximum age in hours (default: 168 = 7 days)

        Returns:
            Number of entries cleared
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                from datetime import timedelta
                expiry_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

                cursor.execute('''
                    DELETE FROM releases_cache
                    WHERE fetched_at < ?
                ''', (expiry_time,))

                deleted = cursor.rowcount
                conn.commit()

                if deleted > 0:
                    logger.info(f"Cleared {deleted} expired cache entries")

                return deleted

        except sqlite3.Error as e:
            logger.error(f"Error clearing expired cache: {e}")
            return 0

    def clear_artist_cache(self, artist_id: str) -> int:
        """
        Clear all cached releases for a specific artist.

        Args:
            artist_id: Spotify artist ID

        Returns:
            Number of entries cleared
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    DELETE FROM releases_cache
                    WHERE artist_id = ?
                ''', (artist_id,))

                deleted = cursor.rowcount
                conn.commit()

                if deleted > 0:
                    logger.info(f"Cleared {deleted} cache entries for artist {artist_id}")

                return deleted

        except sqlite3.Error as e:
            logger.error(f"Error clearing artist cache: {e}")
            return 0

    def cache_isrc_lookup(self, isrc: str, earliest_date: str, earliest_album_name: str) -> bool:
        """
        Cache an ISRC lookup result (immutable, permanent cache).

        Args:
            isrc: International Standard Recording Code
            earliest_date: Earliest release date (YYYY-MM-DD)
            earliest_album_name: Name of the earliest album

        Returns:
            True if cached successfully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cached_at = datetime.now().isoformat()

                cursor.execute('''
                    INSERT OR REPLACE INTO isrc_lookup_cache
                    (isrc, earliest_date, earliest_album_name, cached_at)
                    VALUES (?, ?, ?, ?)
                ''', (isrc, earliest_date, earliest_album_name, cached_at))

                conn.commit()
                return True

        except sqlite3.Error as e:
            logger.error(f"Error caching ISRC lookup for '{isrc}': {e}")
            return False

    def get_cached_isrc_lookup(self, isrc: str) -> Optional[Tuple[str, str]]:
        """
        Get cached ISRC lookup result.

        Args:
            isrc: International Standard Recording Code

        Returns:
            Tuple of (earliest_date, earliest_album_name) or None if not cached
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT earliest_date, earliest_album_name
                    FROM isrc_lookup_cache
                    WHERE isrc = ?
                ''', (isrc,))

                row = cursor.fetchone()
                if row:
                    return (row[0], row[1])
                return None

        except sqlite3.Error as e:
            logger.error(f"Error fetching cached ISRC lookup for '{isrc}': {e}")
            return None
