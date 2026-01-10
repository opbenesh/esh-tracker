import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from artist_tracker.tracker import SpotifyReleaseTracker

class TestTrackerPreview(unittest.TestCase):
    def setUp(self):
        with patch('artist_tracker.tracker.SpotifyClientCredentials'):
            with patch('artist_tracker.tracker.spotipy.Spotify'):
                self.tracker = SpotifyReleaseTracker("fake_id", "fake_secret")
                # Mock the spotipy client
                self.tracker.sp = MagicMock()

    def test_track_artist_success(self):
        # Mock search response
        self.tracker.sp.search.return_value = {
            'artists': {'items': [{'id': 'artist_id', 'name': 'Test Artist'}]}
        }
        # Mock artist response (for name canonicalization)
        self.tracker.sp.artist.return_value = {'name': 'Test Artist'}
        
        # Mock releases response (mocking internal helper or API calls)
        # Since _process_artist calls _get_recent_releases which calls artist_albums...
        # Let's mock _get_recent_releases directly to simplify, as we tested that separately
        
        mock_releases = [
            {
                'artist': 'Test Artist',
                'track': 'New Song',
                'album': 'New Album',
                'release_date': '2025-12-01',
                'popularity': 50
            },
            {
                'artist': 'Test Artist',
                'track': 'Old Song',
                'album': 'Old Album',
                'release_date': '2025-11-01', 
                'popularity': 60
            }
        ]
        
        with patch.object(self.tracker, '_get_recent_releases', return_value=mock_releases) as mock_get_releases:
            results = self.tracker.track_artist('Test Artist')
            
            # Verify search called (indirectly via _process_artist -> _search_artist)
            # Actually _process_artist calls _search_artist which calls sp.search
            
            self.assertEqual(results['total_releases'], 2)
            self.assertEqual(results['artist_name'], 'Test Artist')
            self.assertTrue(results['artist_tracked'])
            self.assertEqual(results['releases'][0]['track'], 'New Song') # Sorted by date

    def test_track_artist_not_found(self):
        # Mock search returning empty
        self.tracker.sp.search.return_value = {'artists': {'items': []}}
        
        results = self.tracker.track_artist('NonExistent')
        
        # Current implementation treats not found as empty results (to support batch processing flow)
        # Wait, if not found, track_artist returns error dict
        # See code:
        # if not artist_name: return {'releases': [], ... 'error': ...}

        # Wait, _process_artist returns (artist_name, []) if not found?
        # Let's check _process_artist:
        # if artist_name and not artist_id: search... if not artist_id: return artist_name, []
        # So it returns name and empty list.

        # BUT wait, _search_artist returns None if not found.
        # _process_artist:
        # artist_id = self._search_artist(artist_name)
        # if not artist_id: return artist_name, []

        # So artist_name is returned.

        # In track_artist:
        # artist_name, releases = self._process_artist(...)
        # if not artist_name: ... error

        # So if I pass 'NonExistent', _parse_artist_input returns (None, 'NonExistent')
        # _process_artist calls _search_artist('NonExistent') -> None
        # returns 'NonExistent', []
        # track_artist sees artist_name='NonExistent', returns success with 0 releases.

        self.assertNotIn('error', results)
        self.assertEqual(results['total_releases'], 0)
        self.assertEqual(results['artist_name'], 'NonExistent')
        self.assertTrue(results['artist_tracked'])

    def test_track_artist_with_limit(self):
         # Mock search response
        self.tracker.sp.search.return_value = {
            'artists': {'items': [{'id': 'artist_id', 'name': 'Test Artist'}]}
        }
        # Mock artist response (for name canonicalization)
        self.tracker.sp.artist.return_value = {'name': 'Test Artist'}
        
        # We need to verify max_tracks is passed to _process_artist and then to _get_recent_releases
        with patch.object(self.tracker, '_get_recent_releases', return_value=[]) as mock_get_releases:
            self.tracker.track_artist('Test Artist', max_tracks_per_artist=5)
            
            mock_get_releases.assert_called_with('artist_id', 'Test Artist', 5)

if __name__ == '__main__':
    unittest.main()
