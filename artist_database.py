#!/usr/bin/env python3
"""
Artist Database Module

Manages SQLite database for storing tracked artists.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ArtistDatabase:
    """Manages artist storage in SQLite database."""

    def __init__(self, db_path: str = 'artists.db'):
        """
        Initialize the artist database.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()

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
        """
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
