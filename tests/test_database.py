#!/usr/bin/env python3
"""
Unit tests for ArtistDatabase.

Comprehensive test suite for database operations.
"""

import os
import sqlite3
import unittest
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from artist_tracker.database import ArtistDatabase
from artist_tracker.exceptions import DatabaseError, ValidationError


class TestArtistDatabase(unittest.TestCase):
    """Test suite for ArtistDatabase."""

    def setUp(self):
        """Set up test database before each test."""
        self.test_db = 'test_artists.db'
        # Remove test database if it exists
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.db = ArtistDatabase(self.test_db)

    def tearDown(self):
        """Clean up test database after each test."""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_init_creates_database(self):
        """Test that database file is created on initialization."""
        self.assertTrue(os.path.exists(self.test_db))

    def test_init_creates_schema(self):
        """Test that schema is created correctly."""
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()

            # Check table exists
            cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='artists'
            ''')
            self.assertIsNotNone(cursor.fetchone())

            # Check columns
            cursor.execute('PRAGMA table_info(artists)')
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            self.assertEqual(columns['id'], 'INTEGER')
            self.assertEqual(columns['date_added'], 'TEXT')
            self.assertEqual(columns['artist_name'], 'TEXT')
            self.assertEqual(columns['spotify_artist_id'], 'TEXT')

    def test_add_artist_success(self):
        """Test adding a new artist."""
        result = self.db.add_artist("Taylor Swift", "06HL4z0CvFAxyc27GXpf02")
        self.assertTrue(result)

        # Verify artist was added
        artists = self.db.get_all_artists()
        self.assertEqual(len(artists), 1)
        self.assertEqual(artists[0][2], "Taylor Swift")
        self.assertEqual(artists[0][3], "06HL4z0CvFAxyc27GXpf02")

    def test_add_artist_duplicate(self):
        """Test adding duplicate artist returns False."""
        self.db.add_artist("Taylor Swift", "06HL4z0CvFAxyc27GXpf02")
        result = self.db.add_artist("Taylor Swift", "06HL4z0CvFAxyc27GXpf02")
        self.assertFalse(result)

        # Verify only one artist exists
        artists = self.db.get_all_artists()
        self.assertEqual(len(artists), 1)

    def test_add_artist_same_name_different_id(self):
        """Test adding artists with same name but different IDs."""
        result1 = self.db.add_artist("John Smith", "1234567890123456789012")
        result2 = self.db.add_artist("John Smith", "abcdefghijklmnopqrstuv")

        self.assertTrue(result1)
        self.assertTrue(result2)

        artists = self.db.get_all_artists()
        self.assertEqual(len(artists), 2)

    def test_add_artist_date_added(self):
        """Test that date_added is set correctly."""
        before = datetime.now()
        self.db.add_artist("Test Artist", "1234567890123456789012")
        after = datetime.now()

        artists = self.db.get_all_artists()
        date_added = datetime.fromisoformat(artists[0][1])

        self.assertGreaterEqual(date_added, before)
        self.assertLessEqual(date_added, after)

    def test_add_artists_batch_success(self):
        """Test batch adding multiple artists."""
        artists = [
            ("Taylor Swift", "06HL4z0CvFAxyc27GXpf02"),
            ("Ed Sheeran", "6eUKZXaKkcviH0Ku9w2n3V"),
            ("Drake", "3TVXtAsR1Inumwj472S9r4")
        ]

        added, skipped = self.db.add_artists_batch(artists)

        self.assertEqual(added, 3)
        self.assertEqual(skipped, 0)
        self.assertEqual(self.db.get_artist_count(), 3)

    def test_add_artists_batch_with_duplicates(self):
        """Test batch adding with some duplicates."""
        # Add one artist first
        self.db.add_artist("Taylor Swift", "06HL4z0CvFAxyc27GXpf02")

        artists = [
            ("Taylor Swift", "06HL4z0CvFAxyc27GXpf02"),  # Duplicate
            ("Ed Sheeran", "6eUKZXaKkcviH0Ku9w2n3V"),    # New
            ("Drake", "3TVXtAsR1Inumwj472S9r4")           # New
        ]

        added, skipped = self.db.add_artists_batch(artists)

        self.assertEqual(added, 2)
        self.assertEqual(skipped, 1)
        self.assertEqual(self.db.get_artist_count(), 3)

    def test_get_all_artists_empty(self):
        """Test getting all artists when database is empty."""
        artists = self.db.get_all_artists()
        self.assertEqual(len(artists), 0)

    def test_get_all_artists_ordering(self):
        """Test that artists are returned in reverse chronological order."""
        # Add artists with slight delay
        self.db.add_artist("Artist 1", "test100000000000000000")
        self.db.add_artist("Artist 2", "test200000000000000000")
        self.db.add_artist("Artist 3", "test300000000000000000")

        artists = self.db.get_all_artists()

        # Most recent should be first
        self.assertEqual(artists[0][2], "Artist 3")
        self.assertEqual(artists[1][2], "Artist 2")
        self.assertEqual(artists[2][2], "Artist 1")

    def test_get_artist_ids(self):
        """Test getting list of artist IDs."""
        self.db.add_artist("Artist 1", "test100000000000000000")
        self.db.add_artist("Artist 2", "test200000000000000000")
        self.db.add_artist("Artist 3", "test300000000000000000")

        ids = self.db.get_artist_ids()

        self.assertEqual(len(ids), 3)
        self.assertIn("test100000000000000000", ids)
        self.assertIn("test200000000000000000", ids)
        self.assertIn("test300000000000000000", ids)

    def test_get_artist_by_id_exists(self):
        """Test getting an artist by Spotify ID when it exists."""
        self.db.add_artist("Taylor Swift", "06HL4z0CvFAxyc27GXpf02")

        artist = self.db.get_artist_by_id("06HL4z0CvFAxyc27GXpf02")

        self.assertIsNotNone(artist)
        self.assertEqual(artist[2], "Taylor Swift")
        self.assertEqual(artist[3], "06HL4z0CvFAxyc27GXpf02")

    def test_get_artist_by_id_not_exists(self):
        """Test getting an artist by ID when it doesn't exist."""
        artist = self.db.get_artist_by_id("nonexistent")
        self.assertIsNone(artist)

    def test_remove_artist_success(self):
        """Test removing an existing artist."""
        self.db.add_artist("Taylor Swift", "06HL4z0CvFAxyc27GXpf02")

        result = self.db.remove_artist("06HL4z0CvFAxyc27GXpf02")

        self.assertTrue(result)
        self.assertEqual(self.db.get_artist_count(), 0)

    def test_remove_artist_not_exists(self):
        """Test removing a non-existent artist."""
        result = self.db.remove_artist("nonexistent")
        self.assertFalse(result)

    def test_get_artist_count_empty(self):
        """Test count when database is empty."""
        count = self.db.get_artist_count()
        self.assertEqual(count, 0)

    def test_get_artist_count_with_artists(self):
        """Test count with multiple artists."""
        self.db.add_artist("Artist 1", "test100000000000000000")
        self.db.add_artist("Artist 2", "test200000000000000000")
        self.db.add_artist("Artist 3", "test300000000000000000")

        count = self.db.get_artist_count()
        self.assertEqual(count, 3)

    def test_clear_all_artists_empty(self):
        """Test clearing when database is empty."""
        count = self.db.clear_all_artists()
        self.assertEqual(count, 0)

    def test_clear_all_artists_with_data(self):
        """Test clearing database with artists."""
        self.db.add_artist("Artist 1", "test100000000000000000")
        self.db.add_artist("Artist 2", "test200000000000000000")
        self.db.add_artist("Artist 3", "test300000000000000000")

        count = self.db.clear_all_artists()

        self.assertEqual(count, 3)
        self.assertEqual(self.db.get_artist_count(), 0)

    def test_concurrent_writes(self):
        """Test thread safety of database operations."""
        def add_artist(i):
            # Generate valid 22-char ID
            artist_id = f"test{i:018d}"  # Pad with zeros to make 22 chars
            return self.db.add_artist(f"Artist {i}", artist_id)

        # Add 20 artists concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(add_artist, range(20)))

        # All should succeed
        self.assertEqual(sum(results), 20)
        self.assertEqual(self.db.get_artist_count(), 20)

    def test_concurrent_reads(self):
        """Test concurrent read operations."""
        # Add some artists
        for i in range(10):
            artist_id = f"test{i:018d}"  # Pad with zeros to make 22 chars
            self.db.add_artist(f"Artist {i}", artist_id)

        def read_operations():
            count = self.db.get_artist_count()
            artists = self.db.get_all_artists()
            ids = self.db.get_artist_ids()
            return (count, len(artists), len(ids))

        # Read concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(lambda _: read_operations(), range(10)))

        # All reads should return consistent results
        for count, artists_len, ids_len in results:
            self.assertEqual(count, 10)
            self.assertEqual(artists_len, 10)
            self.assertEqual(ids_len, 10)

    def test_unicode_artist_names(self):
        """Test handling of Unicode characters in artist names."""
        artists = [
            ("Бо́рис Борисович Гребенщиков", "test100000000000000000"),  # Russian
            ("椎名林檎", "test200000000000000000"),  # Japanese
            ("Björk", "test300000000000000000"),  # Icelandic
            ("Ángel", "test400000000000000000"),  # Spanish
        ]

        for name, artist_id in artists:
            result = self.db.add_artist(name, artist_id)
            self.assertTrue(result)

        # Verify all were added
        all_artists = self.db.get_all_artists()
        self.assertEqual(len(all_artists), 4)

    def test_long_artist_name(self):
        """Test handling of very long artist names (max 500 chars)."""
        # Test maximum allowed length
        long_name = "A" * 500
        result = self.db.add_artist(long_name, "test100000000000000000")
        self.assertTrue(result)

        artist = self.db.get_artist_by_id("test100000000000000000")
        self.assertEqual(artist[2], long_name)

    def test_too_long_artist_name(self):
        """Test that artist names over 500 characters raise ValidationError."""
        too_long_name = "A" * 501  # Over limit
        with self.assertRaises(ValidationError) as context:
            self.db.add_artist(too_long_name, "test200000000000000000")
        self.assertIn('too long', str(context.exception).lower())

    def test_special_characters_in_id(self):
        """Test handling of various valid Spotify IDs."""
        # Spotify IDs are base62 encoded (alphanumeric), exactly 22 characters
        special_ids = [
            "0" * 22,  # All zeros
            "z" * 22,  # All lowercase z's
            "Z" * 22,  # All uppercase Z's
            "aB1cD2eF3gH4iJ5kL6mN78",  # Mixed case and numbers (22 chars)
        ]

        for i, artist_id in enumerate(special_ids):
            result = self.db.add_artist(f"Artist {i}", artist_id)
            self.assertTrue(result)

        self.assertEqual(self.db.get_artist_count(), len(special_ids))

    def test_database_persistence(self):
        """Test that data persists across database reconnections."""
        # Add artist
        self.db.add_artist("Test Artist", "test123000000000000000")

        # Create new database connection
        db2 = ArtistDatabase(self.test_db)

        # Verify artist exists
        artist = db2.get_artist_by_id("test123000000000000000")
        self.assertIsNotNone(artist)
        self.assertEqual(artist[2], "Test Artist")


class TestArtistDatabaseEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test database before each test."""
        self.test_db = 'test_edge_cases.db'
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.db = ArtistDatabase(self.test_db)

    def tearDown(self):
        """Clean up test database after each test."""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_empty_batch_add(self):
        """Test adding empty batch of artists."""
        added, skipped = self.db.add_artists_batch([])
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 0)

    def test_whitespace_handling(self):
        """Test handling of whitespace in artist names."""
        # Name with leading/trailing whitespace
        self.db.add_artist("  Taylor Swift  ", "test100000000000000000")

        artist = self.db.get_artist_by_id("test100000000000000000")
        self.assertEqual(artist[2], "  Taylor Swift  ")  # Whitespace preserved

    def test_empty_string_artist_name(self):
        """Test adding artist with empty string name raises ValidationError."""
        with self.assertRaises(ValidationError) as context:
            self.db.add_artist("", "test100000000000000000")
        self.assertIn('empty', str(context.exception).lower())

    def test_empty_string_artist_id(self):
        """Test adding artist with empty string ID raises ValidationError."""
        with self.assertRaises(ValidationError) as context:
            self.db.add_artist("Test", "")
        self.assertIn('empty', str(context.exception).lower())

    def test_sql_injection_attempt(self):
        """Test that SQL injection attempts are prevented."""
        malicious_input = "'; DROP TABLE artists; --"

        # Should be safely handled by parameterized queries
        result = self.db.add_artist(malicious_input, "test100000000000000000")
        self.assertTrue(result)

        # Table should still exist
        artists = self.db.get_all_artists()
        self.assertEqual(len(artists), 1)
        self.assertEqual(artists[0][2], malicious_input)


if __name__ == '__main__':
    unittest.main()
