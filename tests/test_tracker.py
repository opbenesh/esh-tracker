#!/usr/bin/env python3
"""
Unit tests for Spotify Release Tracker.

All tests use mocked Spotify API - no network calls are made.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, mock_open
from artist_tracker.tracker import SpotifyReleaseTracker
from artist_tracker.exceptions import SpotifyAPIError


class TestSpotifyReleaseTracker(unittest.TestCase):
    """Test suite for SpotifyReleaseTracker."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the SpotifyClientCredentials to prevent network calls
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret'
                )
                # Mock the Spotify client
                self.tracker.sp = Mock()

    def test_parse_artist_input_name(self):
        """Test parsing artist name input."""
        artist_id, artist_name = self.tracker._parse_artist_input('Taylor Swift')
        self.assertIsNone(artist_id)
        self.assertEqual(artist_name, 'Taylor Swift')

    def test_parse_artist_input_uri(self):
        """Test parsing Spotify URI input."""
        artist_id, artist_name = self.tracker._parse_artist_input(
            'spotify:artist:06HL4z0CvFAxyc27GXpf02'
        )
        self.assertEqual(artist_id, '06HL4z0CvFAxyc27GXpf02')
        self.assertIsNone(artist_name)

    def test_parse_artist_input_comment(self):
        """Test parsing comment lines."""
        artist_id, artist_name = self.tracker._parse_artist_input('# Comment')
        self.assertIsNone(artist_id)
        self.assertIsNone(artist_name)

    def test_parse_artist_input_empty(self):
        """Test parsing empty lines."""
        artist_id, artist_name = self.tracker._parse_artist_input('')
        self.assertIsNone(artist_id)
        self.assertIsNone(artist_name)

    def test_parse_release_date_full(self):
        """Test parsing full date (YYYY-MM-DD)."""
        date = self.tracker._parse_release_date('2024-03-15')
        self.assertEqual(date, datetime(2024, 3, 15))

    def test_parse_release_date_year_month(self):
        """Test parsing year-month date (YYYY-MM)."""
        date = self.tracker._parse_release_date('2024-03')
        # Should default to first day of month
        self.assertEqual(date, datetime(2024, 3, 1))

    def test_parse_release_date_year_only(self):
        """Test parsing year-only date (YYYY)."""
        date = self.tracker._parse_release_date('2024')
        # Should default to January 1st
        self.assertEqual(date, datetime(2024, 1, 1))

    def test_parse_release_date_invalid(self):
        """Test parsing invalid date."""
        date = self.tracker._parse_release_date('invalid-date')
        self.assertIsNone(date)

    @patch('artist_tracker.tracker.datetime')
    def test_lookback_window_boundary_keep(self, mock_datetime):
        """Test that releases exactly 90 days ago are kept."""
        # Fixed current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        # Reinitialize tracker with mocked date
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                tracker = SpotifyReleaseTracker('test_id', 'test_secret')
                tracker.sp = Mock()

        # Date exactly 90 days ago: 2024-03-03
        cutoff = datetime(2024, 6, 1) - timedelta(days=90)
        self.assertEqual(cutoff.date(), datetime(2024, 3, 3).date())

        # Release on 2024-03-03 should be kept
        release_date = datetime(2024, 3, 3)
        self.assertGreaterEqual(release_date, tracker.cutoff_date)

    @patch('artist_tracker.tracker.datetime')
    def test_lookback_window_boundary_discard(self, mock_datetime):
        """Test that releases 91 days ago are discarded."""
        # Fixed current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        # Reinitialize tracker with mocked date
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                tracker = SpotifyReleaseTracker('test_id', 'test_secret')
                tracker.sp = Mock()

        # Date 91 days ago: 2024-03-02
        old_date = datetime(2024, 6, 1) - timedelta(days=91)
        self.assertEqual(old_date.date(), datetime(2024, 3, 2).date())

        # Release on 2024-03-02 should be discarded
        release_date = datetime(2024, 3, 2)
        self.assertLess(release_date, tracker.cutoff_date)

    def test_is_noise_live(self):
        """Test noise detection for 'Live' keyword."""
        self.assertTrue(self.tracker._is_noise('Song Name (Live)'))
        self.assertTrue(self.tracker._is_noise('LIVE Performance'))
        self.assertFalse(self.tracker._is_noise('Regular Song'))

    def test_is_noise_remaster(self):
        """Test noise detection for 'Remaster' keyword."""
        self.assertTrue(self.tracker._is_noise('Classic Song - Remastered'))
        self.assertTrue(self.tracker._is_noise('2024 REMASTER'))
        self.assertFalse(self.tracker._is_noise('New Release'))

    def test_is_noise_demo(self):
        """Test noise detection for 'Demo' keyword."""
        self.assertTrue(self.tracker._is_noise('Song Demo'))
        self.assertFalse(self.tracker._is_noise('Love Story'))

    def test_is_noise_multiple_keywords(self):
        """Test noise detection with multiple keywords."""
        self.assertTrue(self.tracker._is_noise('Song (Live Remastered)'))
        self.assertTrue(self.tracker._is_noise('Demo - Instrumental'))

    def test_search_artist_success(self):
        """Test successful artist search."""
        # Mock successful search
        self.tracker.sp.search.return_value = {
            'artists': {
                'items': [
                    {
                        'id': 'artist123',
                        'name': 'Taylor Swift'
                    }
                ]
            }
        }

        artist_id = self.tracker._search_artist('Taylor Swift')
        self.assertEqual(artist_id, 'artist123')
        self.tracker.sp.search.assert_called_once()

    def test_search_artist_not_found(self):
        """Test artist search with no results."""
        # Mock empty search results
        self.tracker.sp.search.return_value = {
            'artists': {
                'items': []
            }
        }

        artist_id = self.tracker._search_artist('NonexistentArtist')
        self.assertIsNone(artist_id)

    def test_get_artist_name_success(self):
        """Test getting artist name by ID."""
        # Mock artist fetch
        self.tracker.sp.artist.return_value = {
            'name': 'Taylor Swift',
            'id': 'artist123'
        }

        name = self.tracker._get_artist_name('artist123')
        self.assertEqual(name, 'Taylor Swift')

    @patch('artist_tracker.tracker.datetime')
    def test_isrc_deduplication(self, mock_datetime):
        """Test ISRC-based deduplication."""
        # Fixed current date
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                tracker = SpotifyReleaseTracker('test_id', 'test_secret')
                tracker.sp = Mock()

        # Mock albums with duplicate ISRCs
        tracker.sp.artist_albums.return_value = {
            'items': [
                {
                    'id': 'album1',
                    'name': 'Single Release',
                    'release_date': '2024-05-15',
                    'album_type': 'single',
                    'external_urls': {'spotify': 'https://open.spotify.com/album/1'}
                },
                {
                    'id': 'album2',
                    'name': 'Full Album',
                    'release_date': '2024-05-20',
                    'album_type': 'album',
                    'external_urls': {'spotify': 'https://open.spotify.com/album/2'}
                }
            ],
            'next': None
        }

        # Mock album tracks - same song on both releases
        def mock_album_tracks(album_id):
            if album_id == 'album1':
                return {
                    'items': [
                        {'id': 'track1', 'name': 'Great Song'}
                    ]
                }
            else:  # album2
                return {
                    'items': [
                        {'id': 'track2', 'name': 'Great Song'}  # Same song
                    ]
                }

        tracker.sp.album_tracks.side_effect = mock_album_tracks

        # Mock track details with same ISRC
        def mock_track(track_id):
            return {
                'id': track_id,
                'name': 'Great Song',
                'external_ids': {'isrc': 'USABC1234567'},  # Same ISRC
                'external_urls': {'spotify': f'https://open.spotify.com/track/{track_id}'},
                'artists': [{'id': 'artist123', 'name': 'Test Artist'}]
            }

        tracker.sp.track.side_effect = mock_track

        # Get releases
        releases = tracker._get_recent_releases('artist123', 'Test Artist')

        # Should only get 1 release due to ISRC deduplication
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]['isrc'], 'USABC1234567')

    @patch('artist_tracker.tracker.datetime')
    def test_get_recent_releases_integration(self, mock_datetime):
        """Integration test for getting recent releases."""
        # Fixed current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                tracker = SpotifyReleaseTracker('test_id', 'test_secret')
                tracker.sp = Mock()

        # Mock albums
        tracker.sp.artist_albums.return_value = {
            'items': [
                {
                    'id': 'album1',
                    'name': 'Recent Album',
                    'release_date': '2024-05-15',
                    'album_type': 'album',
                },
                {
                    'id': 'album2',
                    'name': 'Old Album',
                    'release_date': '2023-01-01',  # Too old
                    'album_type': 'album',
                },
                {
                    'id': 'album3',
                    'name': 'Live Performance',  # Noise
                    'release_date': '2024-05-20',
                    'album_type': 'album',
                }
            ],
            'next': None
        }

        # Mock album tracks
        def mock_album_tracks(album_id):
            return {
                'items': [
                    {'id': f'{album_id}_track1', 'name': f'Track from {album_id}'}
                ]
            }

        tracker.sp.album_tracks.side_effect = mock_album_tracks

        # Mock track details
        def mock_track(track_id):
            return {
                'id': track_id,
                'name': f'Track {track_id}',
                'external_ids': {'isrc': f'ISRC{track_id}'},
                'external_urls': {'spotify': f'https://open.spotify.com/track/{track_id}'},
                'artists': [{'id': 'artist123', 'name': 'Test Artist'}]
            }

        tracker.sp.track.side_effect = mock_track

        # Get releases
        releases = tracker._get_recent_releases('artist123', 'Test Artist')

        # Should only get 1 release (album1)
        # album2 is too old, album3 contains "Live"
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]['album'], 'Recent Album')

    def test_track_from_playlists_success(self):
        """Test successful playlist import/track."""
        # Mock playlist tracks
        self.tracker.sp.playlist_tracks.return_value = {
            'items': [
                {
                    'track': {
                        'artists': [
                            {'id': 'artist1', 'name': 'Artist One'},
                            {'id': 'artist2', 'name': 'Artist Two'}
                        ]
                    }
                }
            ],
            'next': None
        }

        # Mock _track_artists_common to avoid threading logic in this unit test
        with patch.object(self.tracker, '_track_artists_common') as mock_common:
            mock_common.return_value = {}

            self.tracker.track_from_playlists(['playlist123'])

            self.tracker.sp.playlist_tracks.assert_called_once_with('playlist123')
            mock_common.assert_called_once()
            args, _ = mock_common.call_args
            self.assertEqual(len(args[0]), 2) # 2 artists

    def test_track_from_playlists_pagination(self):
        """Test playlist import with pagination."""
        # Mock first page
        self.tracker.sp.playlist_tracks.return_value = {
            'items': [
                {
                    'track': {
                        'artists': [{'id': 'artist1', 'name': 'Artist One'}]
                    }
                }
            ],
            'next': 'https://api.spotify.com/v1/playlists/123/tracks?offset=1'
        }

        # Mock second page
        self.tracker.sp.next.return_value = {
            'items': [
                {
                    'track': {
                        'artists': [{'id': 'artist2', 'name': 'Artist Two'}]
                    }
                }
            ],
            'next': None
        }

        # Mock _track_artists_common
        with patch.object(self.tracker, '_track_artists_common') as mock_common:
            mock_common.return_value = {}

            self.tracker.track_from_playlists(['playlist123'])

            self.tracker.sp.playlist_tracks.assert_called_once()
            self.tracker.sp.next.assert_called_once()
            mock_common.assert_called_once()
            args, _ = mock_common.call_args
            self.assertEqual(len(args[0]), 2)


class TestDateBoundaries(unittest.TestCase):
    """Specific tests for the 90-day boundary as per spec."""

    @patch('artist_tracker.tracker.datetime')
    @patch('artist_tracker.tracker.SpotifyClientCredentials')
    @patch('artist_tracker.tracker.spotipy.Spotify')
    def test_spec_example_90_days_keep(self, mock_spotify, mock_creds, mock_datetime):
        """Test spec example: Date 2024-03-03 (90 days ago) -> KEEP."""
        # Current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        tracker = SpotifyReleaseTracker('test_id', 'test_secret')

        # Cutoff should be 2024-03-03
        expected_cutoff = datetime(2024, 3, 3)
        self.assertEqual(tracker.cutoff_date.date(), expected_cutoff.date())

        # Release on 2024-03-03 should be kept
        release_date = datetime(2024, 3, 3)
        self.assertGreaterEqual(release_date, tracker.cutoff_date)

    @patch('artist_tracker.tracker.datetime')
    @patch('artist_tracker.tracker.SpotifyClientCredentials')
    @patch('artist_tracker.tracker.spotipy.Spotify')
    def test_spec_example_91_days_discard(self, mock_spotify, mock_creds, mock_datetime):
        """Test spec example: Date 2024-03-02 (91 days ago) -> DISCARD."""
        # Current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        tracker = SpotifyReleaseTracker('test_id', 'test_secret')

        # Release on 2024-03-02 (91 days ago) should be discarded
        release_date = datetime(2024, 3, 2)
        self.assertLess(release_date, tracker.cutoff_date)


if __name__ == '__main__':
    unittest.main()


class TestRetryLogic(unittest.TestCase):
    """Test retry logic for API calls."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret'
                )
                self.tracker.sp = Mock()

    @patch('artist_tracker.tracker.time.sleep')
    def test_retry_on_server_error(self, mock_sleep):
        """Test that server errors (5xx) trigger retry."""
        from spotipy.exceptions import SpotifyException
        
        # First call fails with 500, second succeeds
        self.tracker.sp.search.side_effect = [
            SpotifyException(500, -1, 'Server Error'),
            {'artists': {'items': [{'id': 'artist123', 'name': 'Test'}]}}
        ]
        
        result = self.tracker._search_artist('Test Artist')
        
        self.assertEqual(result, 'artist123')
        self.assertEqual(self.tracker.sp.search.call_count, 2)
        mock_sleep.assert_called()  # Should have slept between retries

    @patch('artist_tracker.tracker.time.sleep')
    def test_retry_on_rate_limit(self, mock_sleep):
        """Test rate limit (429) triggers retry with Retry-After header."""
        from spotipy.exceptions import SpotifyException
        
        rate_limit_error = SpotifyException(429, -1, 'Rate Limited')
        rate_limit_error.headers = {'Retry-After': '2'}
        
        # First call rate limited, second succeeds
        self.tracker.sp.search.side_effect = [
            rate_limit_error,
            {'artists': {'items': [{'id': 'artist123', 'name': 'Test'}]}}
        ]
        
        result = self.tracker._search_artist('Test Artist')
        
        self.assertEqual(result, 'artist123')
        self.assertEqual(self.tracker.sp.search.call_count, 2)

    def test_client_error_no_retry(self):
        """Test that client errors (4xx except 429) don't trigger retry."""
        from spotipy.exceptions import SpotifyException
        from artist_tracker.exceptions import SpotifyAPIError
        
        self.tracker.sp.search.side_effect = SpotifyException(400, -1, 'Bad Request')
        
        with self.assertRaises(SpotifyAPIError):
            self.tracker._search_artist('Test Artist')
        
        # Should only be called once (no retry)
        self.assertEqual(self.tracker.sp.search.call_count, 1)


class TestErrorHandling(unittest.TestCase):
    """Test error handling for various failure scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret'
                )
                self.tracker.sp = Mock()

    def test_search_artist_api_error(self):
        """Test that API errors are properly propagated."""
        from spotipy.exceptions import SpotifyException
        from artist_tracker.exceptions import SpotifyAPIError
        
        self.tracker.sp.search.side_effect = SpotifyException(403, -1, 'Forbidden')
        
        with self.assertRaises(SpotifyAPIError):
            self.tracker._search_artist('Test Artist')

    def test_get_artist_name_returns_none_on_error(self):
        """Test that get_artist_name returns None on error."""
        self.tracker.sp.artist.side_effect = Exception('Network Error')
        
        result = self.tracker._get_artist_name('invalid_id')
        
        self.assertIsNone(result)

    def test_get_recent_releases_returns_empty_on_error(self):
        """Test that get_recent_releases returns empty list on error."""
        self.tracker.sp.artist_albums.side_effect = Exception('API Error')
        
        result = self.tracker._get_recent_releases('invalid_id', 'Unknown')
        
        self.assertEqual(result, [])


class TestEarliestReleaseDate(unittest.TestCase):
    """Test ISRC-based earliest release info lookup."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret'
                )
                self.tracker.sp = Mock()

    def test_returns_earliest_date_and_album_from_multiple_releases(self):
        """Test that earliest date and album are returned when track appears on multiple albums."""
        # Mock ISRC search returning track on 3 different albums with different dates
        self.tracker.sp.search.return_value = {
            'tracks': {
                'items': [
                    {
                        'name': 'Test Track',
                        'album': {'name': 'Bundle Release', 'release_date': '2024-05-01'}
                    },
                    {
                        'name': 'Test Track',
                        'album': {'name': 'Second Single', 'release_date': '2024-03-15'}
                    },
                    {
                        'name': 'Test Track',
                        'album': {'name': 'Original Single', 'release_date': '2024-02-01'}  # Earliest
                    }
                ]
            }
        }

        date, album = self.tracker._get_earliest_release_info('TEST123ISRC')

        self.assertIsNotNone(date)
        self.assertEqual(date.date(), datetime(2024, 2, 1).date())
        self.assertEqual(album, 'Original Single')

    def test_caches_results(self):
        """Test that ISRC lookups are cached to avoid redundant API calls."""
        self.tracker.sp.search.return_value = {
            'tracks': {
                'items': [
                    {'name': 'Track', 'album': {'name': 'Album', 'release_date': '2024-05-01'}}
                ]
            }
        }

        # Call twice with same ISRC
        self.tracker._get_earliest_release_info('CACHED_ISRC')
        self.tracker._get_earliest_release_info('CACHED_ISRC')

        # Should only call API once due to caching
        self.assertEqual(self.tracker.sp.search.call_count, 1)

    def test_returns_none_tuple_on_no_results(self):
        """Test that (None, None) is returned when ISRC search finds no tracks."""
        self.tracker.sp.search.return_value = {
            'tracks': {'items': []}
        }

        date, album = self.tracker._get_earliest_release_info('UNKNOWN_ISRC')

        self.assertIsNone(date)
        self.assertIsNone(album)

    def test_returns_none_tuple_on_api_error(self):
        """Test that (None, None) is returned on API error (graceful fallback)."""
        self.tracker.sp.search.side_effect = Exception('API Error')

        date, album = self.tracker._get_earliest_release_info('ERROR_ISRC')

        self.assertIsNone(date)
        self.assertIsNone(album)


class TestOutputFormatters(unittest.TestCase):
    """Test output formatting functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_releases = [
            {
                'artist': 'Test Artist',
                'album': 'Test Album',
                'track': 'Test Track',
                'release_date': '2024-05-15',
                'album_type': 'single',
                'isrc': 'TEST123',
                'spotify_url': 'https://spotify.com/track/1',
                'popularity': 75
            }
        ]

    def test_format_releases_tsv(self):
        """Test TSV formatting."""
        from artist_tracker.tracker import format_releases_tsv
        output = format_releases_tsv(self.sample_releases)
        self.assertIn('2024-05-15', output)
        self.assertIn('Test Artist', output)
        self.assertIn('Test Track', output)
        self.assertIn('\t', output)  # Should contain tabs

    def test_format_releases_csv(self):
        """Test CSV formatting."""
        from artist_tracker.tracker import format_releases_csv
        output = format_releases_csv(self.sample_releases)
        self.assertIn('date,artist,track', output)  # Header
        self.assertIn('2024-05-15,Test Artist,Test Track', output)

    def test_format_releases_json(self):
        """Test JSON formatting."""
        from artist_tracker.tracker import format_releases_json
        import json
        meta = {'total': 1, 'cutoff_date': '2024-03-01'}
        output = format_releases_json(self.sample_releases, meta)
        data = json.loads(output)
        self.assertIn('releases', data)
        self.assertIn('meta', data)
        self.assertEqual(len(data['releases']), 1)
        self.assertEqual(data['meta']['total'], 1)

    def test_format_releases_pretty(self):
        """Test pretty formatting."""
        from artist_tracker.tracker import format_releases_pretty
        from unittest.mock import Mock

        # Mock tracker and db
        mock_tracker = Mock()
        mock_tracker.cutoff_date.date.return_value = '2024-03-01'
        mock_tracker.lookback_days = 90
        # format_releases_pretty no longer takes db argument

        output = format_releases_pretty(self.sample_releases, mock_tracker)
        self.assertIn('SPOTIFY RECENT RELEASE TRACKER', output)
        self.assertIn('Test Artist - Test Track', output)
        self.assertIn('🎵', output)


class TestCustomLookbackDays(unittest.TestCase):
    """Test custom lookback days functionality."""

    @patch('artist_tracker.tracker.SpotifyClientCredentials')
    @patch('artist_tracker.tracker.spotipy.Spotify')
    def test_custom_lookback_30_days(self, mock_spotify, mock_creds):
        """Test tracker with custom 30-day lookback."""
        tracker = SpotifyReleaseTracker('test_id', 'test_secret', lookback_days=30)
        self.assertEqual(tracker.lookback_days, 30)
        expected_cutoff = datetime.now() - timedelta(days=30)
        self.assertEqual(tracker.cutoff_date.date(), expected_cutoff.date())

    @patch('artist_tracker.tracker.SpotifyClientCredentials')
    @patch('artist_tracker.tracker.spotipy.Spotify')
    def test_default_lookback_90_days(self, mock_spotify, mock_creds):
        """Test tracker with default 90-day lookback."""
        tracker = SpotifyReleaseTracker('test_id', 'test_secret')
        self.assertEqual(tracker.lookback_days, 90)

    @patch('artist_tracker.tracker.SpotifyClientCredentials')
    @patch('artist_tracker.tracker.spotipy.Spotify')
    def test_custom_lookback_365_days(self, mock_spotify, mock_creds):
        """Test tracker with 1-year lookback."""
        tracker = SpotifyReleaseTracker('test_id', 'test_secret', lookback_days=365)
        self.assertEqual(tracker.lookback_days, 365)
        expected_cutoff = datetime.now() - timedelta(days=365)
        self.assertEqual(tracker.cutoff_date.date(), expected_cutoff.date())


class TestMaxPerArtist(unittest.TestCase):
    """Test max_per_artist functionality."""

    @patch('artist_tracker.tracker.datetime')
    @patch('artist_tracker.tracker.SpotifyClientCredentials')
    @patch('artist_tracker.tracker.spotipy.Spotify')
    def test_max_per_artist_limits_results(self, mock_spotify, mock_creds, mock_datetime):
        """Test that max_per_artist caps results and uses popularity ranking."""
        # Fixed current date
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        tracker = SpotifyReleaseTracker('test_id', 'test_secret')
        tracker.sp = Mock()

        # Mock albums with multiple tracks
        tracker.sp.artist_albums.return_value = {
            'items': [
                {
                    'id': 'album1',
                    'name': 'Test Album',
                    'release_date': '2024-05-15',
                    'album_type': 'album'
                }
            ],
            'next': None
        }

        # Mock album with 5 tracks
        tracker.sp.album_tracks.return_value = {
            'items': [
                {'id': f'track{i}', 'name': f'Track {i}'} for i in range(5)
            ]
        }

        # Mock track details with different popularity
        def mock_track(track_id):
            track_num = int(track_id[-1])
            return {
                'id': track_id,
                'name': f'Track {track_num}',
                'external_ids': {'isrc': f'ISRC{track_num}'},
                'external_urls': {'spotify': f'https://spotify.com/track/{track_id}'},
                'popularity': 100 - (track_num * 10),  # Track 0 = 100, Track 4 = 60
                'artists': [{'id': 'artist123', 'name': 'Test Artist'}]
            }

        tracker.sp.track.side_effect = mock_track

        # Get releases with max_per_artist=2
        releases = tracker._get_recent_releases('artist123', 'Test Artist', max_tracks=2)

        # Should only get 2 most popular tracks
        self.assertEqual(len(releases), 2)
        self.assertEqual(releases[0]['popularity'], 100)  # Most popular
        self.assertEqual(releases[1]['popularity'], 90)   # Second most popular


class TestSmartFilteringWithGroupedAlbums(unittest.TestCase):
    """Test smart filtering when Spotify groups albums by type (albums, singles, compilations)."""

    @patch('artist_tracker.tracker.datetime')
    def test_finds_recent_singles_despite_old_albums_first(self, mock_datetime):
        """
        Regression test for bug where smart filtering stopped too early.

        Spotify returns albums grouped by type (albums, then singles, then compilations),
        NOT chronologically. If an old album appears first, smart filtering should NOT
        stop pagination because recent singles may appear later in the response.

        Reproduces the Megadeth scenario:
        - Old album "The Sick, The Dying… And The Dead!" (2022-09-02) appears first
        - Recent singles from 2025 appear later in the list
        - Smart filtering was incorrectly stopping at the old album
        """
        # Fixed current date: 2026-01-10
        mock_datetime.now.return_value = datetime(2026, 1, 10)
        mock_datetime.strptime = datetime.strptime

        tracker = SpotifyReleaseTracker('test_id', 'test_secret', lookback_days=365)
        tracker.sp = Mock()

        # Mock albums in Spotify's grouped order: old albums first, recent singles later
        tracker.sp.artist_albums.return_value = {
            'items': [
                # Old album appears first (grouped by type: albums)
                {
                    'id': 'old_album',
                    'name': 'The Sick, The Dying… And The Dead!',
                    'release_date': '2022-09-02',  # Before cutoff
                    'album_type': 'album'
                },
                # Recent singles appear later in the list
                {
                    'id': 'single1',
                    'name': 'Let There Be Shred',
                    'release_date': '2025-12-19',  # After cutoff
                    'album_type': 'single'
                },
                {
                    'id': 'single2',
                    'name': 'I Don\'t Care',
                    'release_date': '2025-11-14',  # After cutoff
                    'album_type': 'single'
                }
            ],
            'next': None
        }

        # Mock album tracks
        def mock_album_tracks(album_id):
            return {
                'items': [
                    {'id': f'{album_id}_track1', 'name': f'Track from {album_id}'}
                ]
            }

        tracker.sp.album_tracks.side_effect = mock_album_tracks

        # Mock track details
        def mock_track(track_id):
            # Assign different ISRCs to avoid deduplication
            return {
                'id': track_id,
                'name': f'Track {track_id}',
                'external_ids': {'isrc': f'ISRC{track_id}'},
                'external_urls': {'spotify': f'https://spotify.com/track/{track_id}'},
                'popularity': 50,
                'artists': [{'id': 'artist123', 'name': 'Megadeth'}]
            }

        tracker.sp.track.side_effect = mock_track

        # Mock ISRC search to return empty results (no earlier releases found)
        tracker.sp.search.return_value = {'tracks': {'items': []}}

        # Get releases - should find the 2 recent singles despite old album appearing first
        releases = tracker._get_recent_releases('artist123', 'Megadeth')

        # Should get 2 releases from the recent singles, NOT 0
        self.assertEqual(len(releases), 2,
            "Smart filtering should not stop at old albums when recent singles appear later")

        # Verify we got the recent singles
        release_albums = [r['album'] for r in releases]
        self.assertIn('Let There Be Shred', release_albums)
        self.assertIn('I Don\'t Care', release_albums)


if __name__ == '__main__':
    unittest.main()
