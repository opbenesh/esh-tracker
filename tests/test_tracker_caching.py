import unittest
from unittest.mock import Mock, patch
from artist_tracker.tracker import SpotifyReleaseTracker
from datetime import datetime, timedelta

class TestCaching(unittest.TestCase):
    def setUp(self):
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                # Mock DB to return empty cached releases to force API fetch
                db_mock = Mock()
                db_mock.get_cached_releases.return_value = []

                self.tracker = SpotifyReleaseTracker(
                    client_id='test_client_id',
                    client_secret='test_client_secret',
                    db=db_mock
                )
                self.tracker.sp = Mock()

    @patch('artist_tracker.tracker.datetime')
    def test_cache_release_structure(self, mock_datetime):
        """Test that cached releases contain artist_id, album_id, and track_id."""
        mock_datetime.now.return_value = datetime(2024, 6, 1)
        mock_datetime.strptime = datetime.strptime

        # Update cutoff date to match mocked time so our release isn't filtered out
        self.tracker.cutoff_date = datetime(2024, 6, 1) - timedelta(days=90)

        # Mock dependencies to simulate a found release
        self.tracker.sp.artist_albums.return_value = {
            'items': [{
                'id': 'album123',
                'name': 'Test Album',
                'release_date': '2024-05-15',
                'album_type': 'album'
            }],
            'next': None
        }

        self.tracker.sp.album_tracks.return_value = {
            'items': [{'id': 'track123', 'name': 'Test Track'}]
        }

        self.tracker.sp.track.return_value = {
            'id': 'track123',
            'name': 'Test Track',
            'external_ids': {'isrc': 'ISRC123'},
            'external_urls': {'spotify': 'url'},
            'popularity': 50,
            'artists': [{'id': 'artist123'}]
        }

        # We need to mock _get_earliest_release_info to return None, None to simplify
        with patch.object(self.tracker, '_get_earliest_release_info', return_value=(None, None)):
             self.tracker._get_recent_releases('artist123', 'Test Artist')

        # Check what cache_release was called with
        self.tracker.db.cache_release.assert_called()
        args = self.tracker.db.cache_release.call_args[0][0]

        self.assertEqual(args['artist_id'], 'artist123')
        self.assertEqual(args['album_id'], 'album123')
        self.assertEqual(args['track_id'], 'track123')

if __name__ == '__main__':
    unittest.main()
