#!/usr/bin/env python3
"""
Unit tests for Spotify Release Tracker.

All tests use mocked Spotify API - no network calls are made.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, mock_open
from spotify_tracker import SpotifyReleaseTracker


class TestSpotifyReleaseTracker(unittest.TestCase):
    """Test suite for SpotifyReleaseTracker."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the SpotifyClientCredentials to prevent network calls
        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
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

    @patch('spotify_tracker.datetime')
    def test_lookback_window_boundary_keep(self, mock_datetime):
        """Test that releases exactly 90 days ago are kept."""
        # Fixed current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        # Reinitialize tracker with mocked date
        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
                tracker = SpotifyReleaseTracker('test_id', 'test_secret')
                tracker.sp = Mock()

        # Date exactly 90 days ago: 2024-03-03
        cutoff = datetime(2024, 6, 1) - timedelta(days=90)
        self.assertEqual(cutoff.date(), datetime(2024, 3, 3).date())

        # Release on 2024-03-03 should be kept
        release_date = datetime(2024, 3, 3)
        self.assertGreaterEqual(release_date, tracker.cutoff_date)

    @patch('spotify_tracker.datetime')
    def test_lookback_window_boundary_discard(self, mock_datetime):
        """Test that releases 91 days ago are discarded."""
        # Fixed current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        # Reinitialize tracker with mocked date
        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
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

    @patch('spotify_tracker.datetime')
    def test_isrc_deduplication(self, mock_datetime):
        """Test ISRC-based deduplication."""
        # Fixed current date
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
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
            ]
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
                'external_urls': {'spotify': f'https://open.spotify.com/track/{track_id}'}
            }

        tracker.sp.track.side_effect = mock_track

        # Get releases
        releases = tracker._get_recent_releases('artist123', 'Test Artist')

        # Should only get 1 release due to ISRC deduplication
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]['isrc'], 'USABC1234567')

    @patch('spotify_tracker.datetime')
    def test_get_recent_releases_integration(self, mock_datetime):
        """Integration test for getting recent releases."""
        # Fixed current date: 2024-06-01
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
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
            ]
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
                'external_urls': {'spotify': f'https://open.spotify.com/track/{track_id}'}
            }

        tracker.sp.track.side_effect = mock_track

        # Get releases
        releases = tracker._get_recent_releases('artist123', 'Test Artist')

        # Should only get 1 release (album1)
        # album2 is too old, album3 contains "Live"
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]['album'], 'Recent Album')

    def test_track_artists_missing_file(self):
        """Test handling of missing artists file."""
        results = self.tracker.track_artists('nonexistent_file.txt')
        self.assertIn('error', results)

    @patch('builtins.open', new_callable=mock_open, read_data='Taylor Swift\nspotify:artist:123\n# Comment\n')
    @patch('spotify_tracker.as_completed')
    @patch('spotify_tracker.ThreadPoolExecutor')
    def test_track_artists_integration(self, mock_executor, mock_as_completed, mock_file):
        """Integration test for tracking multiple artists."""
        # Create proper mock futures
        futures = []
        
        def mock_submit(fn, arg):
            mock_future = Mock()
            mock_future._result = fn(arg)
            mock_future.result.return_value = mock_future._result
            futures.append((mock_future, arg))
            return mock_future

        mock_executor_instance = Mock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=None)
        mock_executor_instance.submit.side_effect = mock_submit
        mock_executor.return_value = mock_executor_instance

        # Mock as_completed to just iterate over the futures
        def mock_as_completed_impl(future_dict):
            return iter(future_dict.keys())
        mock_as_completed.side_effect = mock_as_completed_impl

        # Mock the process_artist method
        def mock_process_artist(artist_input):
            if 'Taylor Swift' in artist_input:
                return ('Taylor Swift', [
                    {
                        'artist': 'Taylor Swift',
                        'album': 'Test Album',
                        'track': 'Test Track',
                        'release_date': '2024-05-15',
                        'album_type': 'album',
                        'isrc': 'TEST123',
                        'spotify_url': 'https://spotify.com/track/1'
                    }
                ])
            return (None, [])

        self.tracker._process_artist = mock_process_artist

        results = self.tracker.track_artists('artists.txt')

        self.assertIn('releases', results)
        self.assertIn('total_releases', results)
        self.assertIn('missing_artists', results)
        self.assertEqual(results['total_releases'], 1)

    def test_import_from_playlist_success(self):
        """Test successful playlist import."""
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

        # Mock database batch add
        mock_db = Mock()
        mock_db.add_artists_batch.return_value = (2, 0)

        added, skipped = self.tracker.import_from_playlist('playlist123', mock_db)

        self.assertEqual(added, 2)
        self.assertEqual(skipped, 0)
        self.tracker.sp.playlist_tracks.assert_called_once_with('playlist123')
        mock_db.add_artists_batch.assert_called_once()

    def test_import_from_playlist_pagination(self):
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

        mock_db = Mock()
        mock_db.add_artists_batch.return_value = (2, 0)

        added, skipped = self.tracker.import_from_playlist('playlist123', mock_db)

        self.assertEqual(added, 2)
        self.tracker.sp.playlist_tracks.assert_called_once()
        self.tracker.sp.next.assert_called_once()
        mock_db.add_artists_batch.assert_called_once()


class TestDateBoundaries(unittest.TestCase):
    """Specific tests for the 90-day boundary as per spec."""

    @patch('spotify_tracker.datetime')
    @patch('spotify_tracker.SpotifyClientCredentials')
    @patch('spotify_tracker.spotipy.Spotify')
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

    @patch('spotify_tracker.datetime')
    @patch('spotify_tracker.SpotifyClientCredentials')
    @patch('spotify_tracker.spotipy.Spotify')
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
        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret'
                )
                self.tracker.sp = Mock()

    @patch('spotify_tracker.time.sleep')
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

    @patch('spotify_tracker.time.sleep')
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
        from exceptions import SpotifyAPIError
        
        self.tracker.sp.search.side_effect = SpotifyException(400, -1, 'Bad Request')
        
        with self.assertRaises(SpotifyAPIError):
            self.tracker._search_artist('Test Artist')
        
        # Should only be called once (no retry)
        self.assertEqual(self.tracker.sp.search.call_count, 1)


class TestErrorHandling(unittest.TestCase):
    """Test error handling for various failure scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('spotify_tracker.SpotifyClientCredentials'):
            with patch('spotify_tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret'
                )
                self.tracker.sp = Mock()

    def test_search_artist_api_error(self):
        """Test that API errors are properly propagated."""
        from spotipy.exceptions import SpotifyException
        from exceptions import SpotifyAPIError
        
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

    def test_import_from_playlist_returns_zero_on_error(self):
        """Test that import_from_playlist returns (0, 0) on error."""
        self.tracker.sp.playlist_tracks.side_effect = Exception('Playlist Error')
        
        mock_db = Mock()
        added, skipped = self.tracker.import_from_playlist('invalid_id', mock_db)
        
        self.assertEqual(added, 0)
        self.assertEqual(skipped, 0)


if __name__ == '__main__':
    unittest.main()
