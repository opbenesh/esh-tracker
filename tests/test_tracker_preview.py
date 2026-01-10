import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from artist_tracker.tracker import SpotifyReleaseTracker

class TestTrackerPreview(unittest.TestCase):
    def setUp(self):
        self.tracker = SpotifyReleaseTracker("fake_id", "fake_secret")
        # Mock the spotipy client
        self.tracker.sp = MagicMock()

    def test_track_artist_onetime_success(self):
        # Mock search response
        self.tracker.sp.search.return_value = {
            'artists': {'items': [{'id': 'artist_id', 'name': 'Test Artist'}]}
        }
        
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
            results = self.tracker.track_artist_onetime('Test Artist')
            
            # Verify search called (indirectly via _process_artist -> _search_artist)
            # Actually _process_artist calls _search_artist which calls sp.search
            
            self.assertEqual(results['total_releases'], 2)
            self.assertEqual(results['artist_name'], 'Test Artist')
            self.assertTrue(results['artist_tracked'])
            self.assertEqual(results['releases'][0]['track'], 'New Song') # Sorted by date

    def test_track_artist_onetime_not_found(self):
        # Mock search returning empty
        self.tracker.sp.search.return_value = {'artists': {'items': []}}
        
        results = self.tracker.track_artist_onetime('NonExistent')
        
        # Current implementation treats not found as empty results (to support batch processing flow)
        self.assertNotIn('error', results)
        self.assertEqual(results['total_releases'], 0)
        self.assertEqual(results['artist_name'], 'NonExistent')
        self.assertTrue(results['artist_tracked'])

    def test_track_artist_onetime_with_limit(self):
         # Mock search response
        self.tracker.sp.search.return_value = {
            'artists': {'items': [{'id': 'artist_id', 'name': 'Test Artist'}]}
        }
        
        # We need to verify max_tracks is passed to _process_artist and then to _get_recent_releases
        with patch.object(self.tracker, '_get_recent_releases', return_value=[]) as mock_get_releases:
            self.tracker.track_artist_onetime('Test Artist', max_tracks=5)
            
            mock_get_releases.assert_called_with('artist_id', 'Test Artist', 5)

if __name__ == '__main__':
    unittest.main()
