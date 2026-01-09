#!/usr/bin/env python3
"""
Live integration tests for Spotify Release Tracker.

These tests make REAL API calls to Spotify. They require:
1. Valid credentials in .env (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET)
2. Network connectivity

Run with: python3 -m unittest test_spotify_tracker_live -v
"""

import os
import unittest
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def has_spotify_credentials():
    """Check if Spotify credentials are available."""
    return bool(
        os.getenv('SPOTIPY_CLIENT_ID') and 
        os.getenv('SPOTIPY_CLIENT_SECRET')
    )


# Skip all tests if no credentials
@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveSpotifyAuthentication(unittest.TestCase):
    """Test that authentication works with real credentials."""

    def test_credentials_authenticate_successfully(self):
        """Verify that credentials from .env work with Spotify API."""
        from spotify_tracker import SpotifyReleaseTracker
        
        client_id = os.getenv('SPOTIPY_CLIENT_ID')
        client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
        
        # This should not raise an exception
        tracker = SpotifyReleaseTracker(client_id, client_secret)
        
        # Verify the client was initialized
        self.assertIsNotNone(tracker.sp)
        self.assertIsNotNone(tracker.cutoff_date)


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveArtistSearch(unittest.TestCase):
    """Test artist search with real Spotify data."""

    @classmethod
    def setUpClass(cls):
        """Initialize tracker once for all tests."""
        from spotify_tracker import SpotifyReleaseTracker
        
        cls.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )

    def test_search_existing_artist_taylor_swift(self):
        """Test searching for Taylor Swift returns valid artist ID."""
        artist_id = self.tracker._search_artist('Taylor Swift')
        
        self.assertIsNotNone(artist_id, "Taylor Swift should be found")
        # Spotify IDs are 22 alphanumeric characters
        self.assertEqual(len(artist_id), 22)
        self.assertTrue(artist_id.isalnum())

    def test_search_existing_artist_ed_sheeran(self):
        """Test searching for Ed Sheeran returns valid artist ID."""
        artist_id = self.tracker._search_artist('Ed Sheeran')
        
        self.assertIsNotNone(artist_id, "Ed Sheeran should be found")
        self.assertEqual(len(artist_id), 22)

    def test_search_nonexistent_artist(self):
        """Test searching for gibberish returns None."""
        artist_id = self.tracker._search_artist('xyznonexistentartist12345xyz')
        
        self.assertIsNone(artist_id)

    def test_get_artist_name_from_id(self):
        """Test getting artist name from a known ID."""
        # Taylor Swift's Spotify ID
        taylor_id = '06HL4z0CvFAxyc27GXpf02'
        name = self.tracker._get_artist_name(taylor_id)
        
        self.assertEqual(name, 'Taylor Swift')


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveReleases(unittest.TestCase):
    """Test fetching real releases from Spotify."""

    @classmethod
    def setUpClass(cls):
        """Initialize tracker once for all tests."""
        from spotify_tracker import SpotifyReleaseTracker
        
        cls.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )

    def test_get_releases_for_active_artist(self):
        """Test getting releases for an artist (Drake - typically has recent releases)."""
        # Drake's Spotify ID
        drake_id = '3TVXtAsR1Inumwj472S9r4'
        
        releases = self.tracker._get_recent_releases(drake_id, 'Drake')
        
        # Releases should be a list (may be empty if no recent releases)
        self.assertIsInstance(releases, list)
        
        # If there are releases, verify structure
        for release in releases:
            self.assertIn('artist', release)
            self.assertIn('album', release)
            self.assertIn('track', release)
            self.assertIn('release_date', release)
            self.assertIn('isrc', release)
            self.assertIn('spotify_url', release)

    def test_release_dates_within_lookback_window(self):
        """Verify all returned releases are within the 90-day window."""
        # Taylor Swift's Spotify ID
        taylor_id = '06HL4z0CvFAxyc27GXpf02'
        
        releases = self.tracker._get_recent_releases(taylor_id, 'Taylor Swift')
        
        cutoff = datetime.now() - timedelta(days=90)
        
        for release in releases:
            # Parse release date
            release_date = datetime.strptime(release['release_date'], '%Y-%m-%d')
            self.assertGreaterEqual(
                release_date, 
                cutoff,
                f"Release '{release['track']}' dated {release['release_date']} is older than 90 days"
            )

    def test_isrc_codes_are_valid(self):
        """Verify ISRC codes returned are properly formatted."""
        drake_id = '3TVXtAsR1Inumwj472S9r4'
        
        releases = self.tracker._get_recent_releases(drake_id, 'Drake')
        
        for release in releases:
            isrc = release.get('isrc')
            if isrc:  # Some tracks may not have ISRC
                # ISRC format: 2 letters (country) + 3 chars (registrant) + 2 digits (year) + 5 digits (designation)
                self.assertEqual(len(isrc), 12, f"ISRC '{isrc}' should be 12 characters")


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLivePlaylistImport(unittest.TestCase):
    """Test importing artists from real Spotify playlists."""

    def setUp(self):
        """Initialize tracker and fresh database for each test."""
        from spotify_tracker import SpotifyReleaseTracker
        from artist_database import ArtistDatabase
        import tempfile
        
        self.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )
        # Use temp file database (in-memory doesn't work well with setUpClass)
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db = ArtistDatabase(self.temp_db.name)

    def tearDown(self):
        """Clean up temp database."""
        import os as os_module
        try:
            os_module.unlink(self.temp_db.name)
        except:
            pass

    def test_can_fetch_playlist_tracks(self):
        """Test that we can fetch tracks from a playlist (API format check)."""
        # Use a test approach that doesn't depend on a specific playlist existing
        # Instead, search for a track and verify the API response format
        results = self.tracker.sp.search(q='artist:Taylor Swift', type='track', limit=1)
        
        # Verify search returns expected structure
        self.assertIn('tracks', results)
        self.assertIn('items', results['tracks'])
        
        if results['tracks']['items']:
            track = results['tracks']['items'][0]
            # Verify track has artists
            self.assertIn('artists', track)
            self.assertGreater(len(track['artists']), 0)
            
            artist = track['artists'][0]
            self.assertIn('id', artist)
            self.assertIn('name', artist)

    def test_add_artist_to_database(self):
        """Verify we can add artists to database after discovering them."""
        # Search for an artist
        artist_id = self.tracker._search_artist('Adele')
        self.assertIsNotNone(artist_id)
        
        # Add to database
        added = self.db.add_artist('Adele', artist_id)
        self.assertTrue(added)
        
        # Verify it's in the database
        artist = self.db.get_artist_by_id(artist_id)
        self.assertIsNotNone(artist)
        self.assertEqual(artist[2], 'Adele')

    def test_import_from_playlist_real(self):
        """End-to-end test: import from a real playlist and verify DB."""
        # Use a well-known public playlist
        # ID: 5ABHKGoOzxkaa28ttQV9sE (Top 100 most streamed songs)
        playlist_id = '5ABHKGoOzxkaa28ttQV9sE'
        
        added, skipped = self.tracker.import_from_playlist(playlist_id, self.db)
        
        # We should have added some artists
        self.assertGreater(added + skipped, 0)
        
        # Verify database count
        count = self.db.get_artist_count()
        self.assertEqual(count, added + skipped)


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveEndToEnd(unittest.TestCase):
    """End-to-end test: full workflow from DB to tracking releases."""

    def test_full_workflow_import_and_track(self):
        """Test complete workflow: add artist to DB, then track releases."""
        from spotify_tracker import SpotifyReleaseTracker
        from artist_database import ArtistDatabase
        import tempfile
        
        tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )
        
        # Use temp file database
        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db = ArtistDatabase(temp_db.name)
        
        try:
            # Add a known artist directly
            taylor_id = '06HL4z0CvFAxyc27GXpf02'
            db.add_artist('Taylor Swift', taylor_id)
            
            # Track releases from database
            results = tracker.track_artists_from_db(db)
            
            # Verify result structure
            self.assertIn('releases', results)
            self.assertIn('total_releases', results)
            self.assertIn('artists_processed', results)
            
            # Should have processed 1 artist
            self.assertEqual(results['artists_processed'], 1)
            
            # Releases should be a list inside the results dict
            self.assertIsInstance(results['releases'], list)
            
            # Should have found some releases (Taylor Swift is active)
            self.assertGreater(results['total_releases'], 0, 
                "Taylor Swift should have recent releases")
        finally:
            import os as os_module
            try:
                os_module.unlink(temp_db.name)
            except:
                pass


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")  
class TestAPIResponseFormat(unittest.TestCase):
    """Verify Spotify API responses match expected format."""

    @classmethod
    def setUpClass(cls):
        """Initialize tracker once for all tests."""
        from spotify_tracker import SpotifyReleaseTracker
        
        cls.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )

    def test_artist_albums_response_format(self):
        """Verify artist_albums API response has expected fields."""
        taylor_id = '06HL4z0CvFAxyc27GXpf02'
        
        response = self.tracker.sp.artist_albums(
            taylor_id,
            album_type='album,single',
            limit=1
        )
        
        # Verify response structure
        self.assertIn('items', response)
        
        if response['items']:
            album = response['items'][0]
            self.assertIn('id', album)
            self.assertIn('name', album)
            self.assertIn('release_date', album)
            self.assertIn('album_type', album)

    def test_track_response_format(self):
        """Verify track API response has expected fields including ISRC."""
        # Search for a known track to get its ID
        results = self.tracker.sp.search(q='Shake It Off Taylor Swift', type='track', limit=1)
        
        if results['tracks']['items']:
            track_id = results['tracks']['items'][0]['id']
            track = self.tracker.sp.track(track_id)
            
            # Verify essential fields exist
            self.assertIn('id', track)
            self.assertIn('name', track)
            self.assertIn('external_ids', track)
            self.assertIn('external_urls', track)
            
            # ISRC should be in external_ids
            if 'isrc' in track['external_ids']:
                isrc = track['external_ids']['isrc']
                self.assertEqual(len(isrc), 12)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveImportFromTxt(unittest.TestCase):
    """Test importing artists from text files with real API calls."""

    def setUp(self):
        """Initialize tracker and fresh database for each test."""
        from spotify_tracker import SpotifyReleaseTracker
        from artist_database import ArtistDatabase
        import tempfile
        
        self.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db = ArtistDatabase(self.temp_db.name)
        self.temp_txt = None

    def tearDown(self):
        """Clean up temp files."""
        import os as os_module
        try:
            os_module.unlink(self.temp_db.name)
        except:
            pass
        if self.temp_txt:
            try:
                os_module.unlink(self.temp_txt)
            except:
                pass

    def test_import_txt_with_artist_names(self):
        """End-to-end test: import artists by name from txt file."""
        import tempfile
        
        # Create temp txt file with artist names
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Taylor Swift\n")
            f.write("Ed Sheeran\n")
            f.write("# This is a comment\n")
            f.write("\n")  # Empty line
            f.write("Adele\n")
            self.temp_txt = f.name
        
        added, skipped, failed = self.tracker.import_from_txt(self.temp_txt, self.db)
        
        # Should have added 3 artists
        self.assertEqual(added, 3)
        self.assertEqual(len(failed), 0)
        self.assertEqual(self.db.get_artist_count(), 3)

    def test_import_txt_with_spotify_uris(self):
        """End-to-end test: import artists by Spotify URI from txt file."""
        import tempfile
        
        # Create temp txt file with Spotify URIs
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Taylor Swift's URI
            f.write("spotify:artist:06HL4z0CvFAxyc27GXpf02\n")
            # Ed Sheeran's URI
            f.write("spotify:artist:6eUKZXaKkcviH0Ku9w2n3V\n")
            self.temp_txt = f.name
        
        added, skipped, failed = self.tracker.import_from_txt(self.temp_txt, self.db)
        
        self.assertEqual(added, 2)
        self.assertEqual(len(failed), 0)
        
        # Verify correct artists were added
        artist = self.db.get_artist_by_id('06HL4z0CvFAxyc27GXpf02')
        self.assertIsNotNone(artist)
        self.assertEqual(artist[2], 'Taylor Swift')

    def test_import_txt_with_nonexistent_artist(self):
        """Test that nonexistent artists are reported as failed."""
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Taylor Swift\n")
            f.write("xyznonexistentartist12345xyz\n")
            self.temp_txt = f.name
        
        added, skipped, failed = self.tracker.import_from_txt(self.temp_txt, self.db)
        
        self.assertEqual(added, 1)
        self.assertEqual(len(failed), 1)
        self.assertIn('xyznonexistentartist12345xyz', failed)


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveISRCDeduplication(unittest.TestCase):
    """Test ISRC-based deduplication with real Spotify data."""

    @classmethod
    def setUpClass(cls):
        """Initialize tracker once for all tests."""
        from spotify_tracker import SpotifyReleaseTracker
        
        cls.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )

    def test_isrc_deduplication_removes_duplicates(self):
        """Verify that duplicate ISRCs are filtered out in release results."""
        # Taylor Swift's Spotify ID - she often has singles that appear on albums
        taylor_id = '06HL4z0CvFAxyc27GXpf02'
        
        releases = self.tracker._get_recent_releases(taylor_id, 'Taylor Swift')
        
        # Collect all ISRCs
        isrcs = [r['isrc'] for r in releases if r['isrc'] != 'N/A']
        
        # Verify no duplicate ISRCs (all should be unique)
        self.assertEqual(len(isrcs), len(set(isrcs)), 
            f"Found duplicate ISRCs: {[isrc for isrc in isrcs if isrcs.count(isrc) > 1]}")


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveNoiseFiltering(unittest.TestCase):
    """Test noise filtering (live, remaster, demo, etc.) with real data."""

    @classmethod
    def setUpClass(cls):
        """Initialize tracker once for all tests."""
        from spotify_tracker import SpotifyReleaseTracker
        
        cls.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )

    def test_no_live_versions_in_results(self):
        """Verify that 'Live' versions are filtered out."""
        # Taylor Swift often has live versions
        taylor_id = '06HL4z0CvFAxyc27GXpf02'
        
        releases = self.tracker._get_recent_releases(taylor_id, 'Taylor Swift')
        
        for release in releases:
            album_lower = release['album'].lower()
            track_lower = release['track'].lower()
            self.assertNotIn('live', album_lower, 
                f"Live version found in album: {release['album']}")
            self.assertNotIn('live', track_lower, 
                f"Live version found in track: {release['track']}")

    def test_no_remastered_versions_in_results(self):
        """Verify that remastered versions are filtered out."""
        taylor_id = '06HL4z0CvFAxyc27GXpf02'
        
        releases = self.tracker._get_recent_releases(taylor_id, 'Taylor Swift')
        
        for release in releases:
            album_lower = release['album'].lower()
            track_lower = release['track'].lower()
            self.assertNotIn('remaster', album_lower, 
                f"Remastered found in album: {release['album']}")
            self.assertNotIn('remaster', track_lower, 
                f"Remastered found in track: {release['track']}")


@unittest.skipUnless(has_spotify_credentials(), "No Spotify credentials in .env")
class TestLiveErrorHandling(unittest.TestCase):
    """Test error handling with real API calls."""

    def setUp(self):
        """Initialize tracker and fresh database for each test."""
        from spotify_tracker import SpotifyReleaseTracker
        from artist_database import ArtistDatabase
        import tempfile
        
        self.tracker = SpotifyReleaseTracker(
            os.getenv('SPOTIPY_CLIENT_ID'),
            os.getenv('SPOTIPY_CLIENT_SECRET')
        )
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db = ArtistDatabase(self.temp_db.name)

    def tearDown(self):
        """Clean up temp database."""
        import os as os_module
        try:
            os_module.unlink(self.temp_db.name)
        except:
            pass

    def test_invalid_playlist_id_returns_zero(self):
        """Test that invalid playlist ID returns (0, 0) gracefully."""
        added, skipped = self.tracker.import_from_playlist('invalid_playlist_id_12345', self.db)
        
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 0)

    def test_invalid_artist_id_returns_none(self):
        """Test that invalid artist ID returns None for name lookup."""
        name = self.tracker._get_artist_name('invalid_artist_id_12345')
        
        self.assertIsNone(name)

    def test_releases_for_invalid_artist_returns_empty(self):
        """Test that releases for invalid artist returns empty list."""
        releases = self.tracker._get_recent_releases('invalid_artist_id', 'Unknown')
        
        self.assertEqual(releases, [])


if __name__ == '__main__':
    unittest.main()
