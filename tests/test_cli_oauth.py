#!/usr/bin/env python3
"""
Unit tests for CLI OAuth handling.
"""

import unittest
from unittest.mock import Mock, patch
import os
import sys
from io import StringIO
from artist_tracker.tracker import cmd_track

class TestCmdTrackOAuth(unittest.TestCase):
    def setUp(self):
        self.tracker = Mock()
        self.args = Mock()
        self.args.liked = True
        self.args.artist = None
        self.args.playlists = None
        self.args.max_per_artist = 10
        self.args.format = 'tsv'

        # Mock auth_manager on tracker.sp
        self.tracker.sp = Mock()
        self.auth_manager = Mock()
        self.tracker.sp.auth_manager = self.auth_manager

        # Mock track_liked_songs to return valid result structure
        self.tracker.track_liked_songs.return_value = {
            'releases': [],
            'total_releases': 0,
            'artists_processed': 0
        }

    @patch('artist_tracker.tracker.os.getenv')
    def test_warnings_on_missing_redirect_uri_and_no_token(self, mock_getenv):
        # Simulate missing SPOTIPY_REDIRECT_URI
        def getenv_side_effect(key, default=None):
            if key == 'SPOTIPY_REDIRECT_URI':
                return None
            return default
        mock_getenv.side_effect = getenv_side_effect

        # Mock auth_manager to return invalid token
        self.auth_manager.get_cached_token.return_value = None
        self.auth_manager.validate_token.return_value = None

        # Capture stderr
        captured_stderr = StringIO()
        sys.stderr = captured_stderr

        try:
            cmd_track(self.args, self.tracker)
        finally:
            sys.stderr = sys.__stderr__

        output = captured_stderr.getvalue()
        self.assertIn("Warning: SPOTIPY_REDIRECT_URI is not set", output)
        self.assertIn("default to 'http://localhost:8888/callback'", output)

        # It should still try to track
        self.tracker.track_liked_songs.assert_called_once()

    @patch('artist_tracker.tracker.os.getenv')
    def test_no_warning_if_token_valid(self, mock_getenv):
        # Simulate missing SPOTIPY_REDIRECT_URI
        def getenv_side_effect(key, default=None):
            if key == 'SPOTIPY_REDIRECT_URI':
                return None
            return default
        mock_getenv.side_effect = getenv_side_effect

        # Mock auth_manager to return VALID token
        self.auth_manager.get_cached_token.return_value = {'access_token': 'valid'}
        self.auth_manager.validate_token.return_value = {'access_token': 'valid'}

        # Capture stderr
        captured_stderr = StringIO()
        sys.stderr = captured_stderr

        try:
            cmd_track(self.args, self.tracker)
        finally:
            sys.stderr = sys.__stderr__

        output = captured_stderr.getvalue()
        self.assertNotIn("Warning: SPOTIPY_REDIRECT_URI is not set", output)

        self.tracker.track_liked_songs.assert_called_once()

if __name__ == '__main__':
    unittest.main()
