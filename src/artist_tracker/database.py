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
