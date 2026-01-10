#!/usr/bin/env python3
"""
Spotify Recent Release Tracker

Tracks recent releases (last 90 days) from playlists, specific artists, or Liked Songs.
Uses Client Credentials Flow for public data and OAuth for user data.
Uses SQLite for caching.
"""

import argparse
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union
from dotenv import load_dotenv
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from tqdm import tqdm
from .database import ArtistDatabase
from .exceptions import (
    ArtistNotFoundError,
    PlaylistNotFoundError,
    RateLimitError,
    SpotifyAPIError,
    ValidationError
)
from .profiler import PerformanceStats, ProfilerContext


# Configure logging
def setup_logging(verbose: bool = False):
    """
    Configure logging settings.
    
    Args:
        verbose: If True, show INFO logs on console. Otherwise show WARNING+.
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    root_logger.handlers = []
    
    # File handler - always logs INFO
    file_handler = logging.FileHandler('app.log')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)
    
    # Console handler - logs WARNING by default, INFO if verbose
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)


class DummyContext:
    """Dummy context manager that does nothing (for when profiler is disabled)."""
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class SpotifyReleaseTracker:
    """Tracks recent releases from Spotify artists."""

    # Noise filters - skip releases with these keywords
    NOISE_KEYWORDS = [
        'live', 'remaster', 'demo', 'commentary',
        'instrumental', 'karaoke'
    ]

    # Lookback window in days
    LOOKBACK_DAYS = 90

    # API retry configuration
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2.0  # seconds

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None,
                 lookback_days: Optional[int] = None, profiler: Optional[PerformanceStats] = None,
                 db: Optional[ArtistDatabase] = None, force_refresh: bool = False,
                 spotify_client=None, auth_manager=None):
        """
        Initialize the tracker with Spotify credentials.

        Args:
            client_id: Spotify API client ID (optional if spotify_client or auth_manager provided)
            client_secret: Spotify API client secret (optional if spotify_client or auth_manager provided)
            lookback_days: Optional custom lookback window in days (default: 90)
            profiler: Optional PerformanceStats instance for profiling
            db: Optional ArtistDatabase instance for caching
            force_refresh: If True, bypass cache and fetch fresh data
            spotify_client: Optional pre-configured Spotify client (for testing/mocking)
            auth_manager: Optional pre-configured auth manager (e.g., SpotifyOAuth)
        """
        if spotify_client is not None:
            self.sp = spotify_client
        elif auth_manager is not None:
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
        else:
            if not client_id or not client_secret:
                 raise ValueError("Must provide client_id and client_secret if no client/auth_manager provided")
            auth_manager = SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)

        self.lookback_days = lookback_days if lookback_days is not None else self.LOOKBACK_DAYS
        self.cutoff_date = datetime.now() - timedelta(days=self.lookback_days)
        self.profiler = profiler
        self.db = db
        self.force_refresh = force_refresh
        logger.info(f"Initialized tracker with cutoff date: {self.cutoff_date.date()} ({self.lookback_days} days)")

    def _call_api(self, endpoint: str, func, *args, **kwargs):
        """
        Call Spotify API and record in profiler if enabled.

        Args:
            endpoint: Name of the API endpoint for profiling
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from the API call
        """
        if self.profiler:
            self.profiler.record_api_call(endpoint)

        return func(*args, **kwargs)

    def _retry_on_error(self, func, *args, max_retries: int = None, **kwargs):
        """
        Retry a function call with exponential backoff on error.

        Args:
            func: Function to call
            *args: Positional arguments for the function
            max_retries: Maximum number of retries (default: self.MAX_RETRIES)
            **kwargs: Keyword arguments for the function

        Returns:
            Function result

        Raises:
            SpotifyAPIError: If all retries fail
            RateLimitError: If rate limit is exceeded
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)

            except SpotifyException as e:
                last_exception = e

                # Handle rate limiting
                if e.http_status == 429:
                    retry_after = int(e.headers.get('Retry-After', self.RETRY_BASE_DELAY))
                    logger.warning(
                        f"Rate limit exceeded. Waiting {retry_after}s before retry "
                        f"(attempt {attempt + 1}/{max_retries + 1})"
                    )
                    if attempt < max_retries:
                        time.sleep(retry_after)
                        continue
                    else:
                        raise RateLimitError(retry_after=retry_after) from e

                # Handle server errors (5xx)
                elif e.http_status and 500 <= e.http_status < 600:
                    if attempt < max_retries:
                        wait_time = self.RETRY_BASE_DELAY * (2 ** attempt)
                        logger.warning(
                            f"Server error ({e.http_status}). Retrying in {wait_time}s "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise SpotifyAPIError(f"Server error after {max_retries} retries: {e}",
                                            status_code=e.http_status) from e

                # Handle other HTTP errors
                elif e.http_status and 400 <= e.http_status < 500:
                    # Client errors shouldn't be retried
                    raise SpotifyAPIError(f"API error: {e}", status_code=e.http_status) from e

                # Handle network errors
                else:
                    if attempt < max_retries:
                        wait_time = self.RETRY_BASE_DELAY * (2 ** attempt)
                        logger.warning(
                            f"Network error: {e}. Retrying in {wait_time}s "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise SpotifyAPIError(f"Network error after {max_retries} retries: {e}") from e

            except Exception as e:
                # Unexpected errors shouldn't be retried
                logger.error(f"Unexpected error: {e}")
                raise

        # This should never be reached, but just in case
        raise SpotifyAPIError(f"Failed after {max_retries} retries") from last_exception

    def _parse_artist_input(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse artist input from text file.

        Args:
            line: Input line from artists.txt

        Returns:
            Tuple of (artist_id, artist_name) - one will be None
        """
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            return None, None

        # Check if it's a Spotify URI
        if line.startswith('spotify:artist:'):
            artist_id = line.split(':')[-1]
            return artist_id, None

        # Otherwise treat as artist name
        return None, line

    def _parse_release_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse release date handling partial dates.

        Args:
            date_str: Release date string (YYYY, YYYY-MM, or YYYY-MM-DD)

        Returns:
            Datetime object or None if parsing fails
        """
        try:
            # Handle year only (e.g., "2024")
            if len(date_str) == 4:
                return datetime.strptime(f"{date_str}-01-01", "%Y-%m-%d")

            # Handle year-month (e.g., "2024-03")
            elif len(date_str) == 7:
                return datetime.strptime(f"{date_str}-01", "%Y-%m-%d")

            # Handle full date (e.g., "2024-03-15")
            else:
                return datetime.strptime(date_str, "%Y-%m-%d")

        except ValueError as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None

    def _is_noise(self, title: str) -> bool:
        """
        Check if a release title contains noise keywords.

        Args:
            title: Release or track title

        Returns:
            True if title contains noise keywords
        """
        title_lower = title.lower()
        for keyword in self.NOISE_KEYWORDS:
            if keyword in title_lower:
                return True
        return False

    def _search_artist(self, artist_name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Search for an artist by name and return their ID and official name with retry logic.

        Args:
            artist_name: Name of the artist to search

        Returns:
            Tuple of (Artist ID, Official Name). Both None if not found.

        Raises:
            SpotifyAPIError: If API call fails after retries
        """
        def search_call():
            return self._call_api('search_artist', self.sp.search,
                q=f'artist:{artist_name}',
                type='artist',
                limit=1
            )

        try:
            results = self._retry_on_error(search_call)

            if results['artists']['items']:
                artist = results['artists']['items'][0]
                artist_id = artist['id']
                official_name = artist['name']
                logger.info(f"Found artist '{official_name}' (ID: {artist_id})")
                return artist_id, official_name
            else:
                logger.warning(f"No results found for artist '{artist_name}'")
                return None, None

        except (SpotifyAPIError, RateLimitError) as e:
            logger.error(f"API error searching for artist '{artist_name}': {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error searching for artist '{artist_name}': {e}")
            raise

    def _get_artist_name(self, artist_id: str) -> Optional[str]:
        """
        Get artist name from ID.

        Args:
            artist_id: Spotify artist ID

        Returns:
            Artist name or None if not found
        """
        try:
            artist = self._call_api('artist', self.sp.artist, artist_id)
            return artist['name']
        except Exception as e:
            logger.error(f"Error fetching artist ID '{artist_id}': {e}")
            return None

    def _get_earliest_release_info(self, isrc: str) -> Tuple[Optional[datetime], Optional[str]]:
        """
        Find the earliest release date and album for a track by searching all instances via ISRC.

        This handles the case where artists release singles incrementally (e.g., single1,
        then single2 bundled with single1, etc.) - we want the original release info.

        Args:
            isrc: International Standard Recording Code for the track

        Returns:
            Tuple of (earliest_date, original_album_name), or (None, None) if search fails
        """
        # Check persistent cache first (if database is available)
        if self.db:
            cached_result = self.db.get_cached_isrc_lookup(isrc)
            if cached_result:
                if self.profiler:
                    self.profiler.record_cache_hit()
                # Convert date string back to datetime
                earliest_date = self._parse_release_date(cached_result[0])
                return earliest_date, cached_result[1]

        # Check session cache (avoid redundant API calls within a session)
        if not hasattr(self, '_isrc_info_cache'):
            self._isrc_info_cache: Dict[str, Tuple[Optional[datetime], Optional[str]]] = {}

        if isrc in self._isrc_info_cache:
            if self.profiler:
                self.profiler.record_cache_hit()
            return self._isrc_info_cache[isrc]

        if self.profiler:
            self.profiler.record_cache_miss()

        try:
            # Search for all tracks with this ISRC
            results = self._call_api('search_isrc', self.sp.search, q=f"isrc:{isrc}", type="track", limit=50)

            earliest_date: Optional[datetime] = None
            earliest_album_name: Optional[str] = None

            for track in results.get('tracks', {}).get('items', []):
                album = track.get('album', {})
                release_date_str = album.get('release_date')

                if release_date_str:
                    release_date = self._parse_release_date(release_date_str)
                    if release_date:
                        if earliest_date is None or release_date < earliest_date:
                            earliest_date = release_date
                            earliest_album_name = album.get('name')

            if earliest_date and earliest_album_name:
                logger.debug(
                    f"ISRC {isrc}: earliest release is '{earliest_album_name}' "
                    f"on {earliest_date.strftime('%Y-%m-%d')}"
                )

                # Cache in persistent storage if database is available
                if self.db:
                    try:
                        self.db.cache_isrc_lookup(isrc, earliest_date.strftime('%Y-%m-%d'), earliest_album_name)
                    except Exception as cache_error:
                        logger.warning(f"Failed to cache ISRC lookup for '{isrc}': {cache_error}")

            # Cache the result in session cache
            self._isrc_info_cache[isrc] = (earliest_date, earliest_album_name)
            return earliest_date, earliest_album_name

        except Exception as e:
            logger.warning(f"Error searching ISRC '{isrc}': {e}")
            self._isrc_info_cache[isrc] = (None, None)
            return None, None

    def _get_recent_releases(
        self,
        artist_id: str,
        artist_name: str,
        max_tracks: Optional[int] = None
    ) -> List[Dict]:
        """
        Get recent releases for an artist.

        Args:
            artist_id: Spotify artist ID
            artist_name: Artist name for logging
            max_tracks: Optional cap on number of tracks to return (uses popularity ranking)

        Returns:
            List of release dictionaries with deduplication
        """
        # Check cache first if available and not forcing refresh
        if self.db and not self.force_refresh:
            cutoff_date_str = self.cutoff_date.strftime('%Y-%m-%d')
            cached_releases = self.db.get_cached_releases(artist_id, cutoff_date_str)

            if cached_releases:
                logger.info(f"Using cached releases for artist '{artist_name}' ({len(cached_releases)} releases)")
                if self.profiler:
                    self.profiler.record_cache_hit()

                # Convert cached format to output format
                releases = []
                for cached in cached_releases:
                    releases.append({
                        'artist': artist_name,
                        'album': cached['album_name'],
                        'track': cached['track_name'],
                        'release_date': cached['release_date'],
                        'album_type': cached['album_type'],
                        'isrc': cached['isrc'] or 'N/A',
                        'spotify_url': cached['spotify_url'],
                        'popularity': cached['popularity']
                    })

                # Apply max_tracks cap if specified
                if max_tracks and len(releases) > max_tracks:
                    releases.sort(key=lambda x: x['popularity'], reverse=True)
                    releases = releases[:max_tracks]

                return releases
            else:
                if self.profiler:
                    self.profiler.record_cache_miss()

        seen_isrcs: Set[str] = set()
        releases = []

        try:
            # Get all album types with pagination and early stopping
            with ProfilerContext(self.profiler, 'fetch_artist_albums') if self.profiler else DummyContext():
                albums_response = self._call_api('artist_albums', self.sp.artist_albums,
                    artist_id,
                    album_type='album,single,compilation',
                    limit=50
                )

            albums_to_process = []
            # Process first page - collect albums within cutoff date
            for album in albums_response['items']:
                release_date = self._parse_release_date(album['release_date'])
                if not release_date:
                    continue

                # Skip old albums, but DON'T stop pagination
                # Note: Spotify groups albums by type (albums, singles, compilations),
                # NOT by date, so we must continue checking all pages
                if release_date >= self.cutoff_date:
                    albums_to_process.append((album, release_date))

            # Fetch remaining pages
            while albums_response['next']:
                try:
                    albums_response = self._call_api('artist_albums_next', self.sp.next, albums_response)

                    for album in albums_response['items']:
                        release_date = self._parse_release_date(album['release_date'])
                        if not release_date:
                            continue

                        # Skip old albums, but continue pagination
                        if release_date >= self.cutoff_date:
                            albums_to_process.append((album, release_date))

                except Exception as e:
                    logger.warning(f"Error fetching next page of albums for '{artist_name}': {e}")
                    break

            logger.debug(f"Processing {len(albums_to_process)} albums for '{artist_name}'")

            # Now process the albums we collected
            for album, release_date in albums_to_process:

                # Check for noise in album title
                if self._is_noise(album['name']):
                    logger.info(
                        f"Skipping '{album['name']}' - contains noise keyword"
                    )
                    continue

                # Get tracks from album
                album_id = album['id']
                tracks_response = self._call_api('album_tracks', self.sp.album_tracks, album_id)
                tracks = tracks_response['items']

                for track in tracks:
                    # Check for noise in track title
                    if self._is_noise(track['name']):
                        logger.info(
                            f"Skipping track '{track['name']}' - contains noise keyword"
                        )
                        continue

                    # Get ISRC for deduplication
                    # Need to fetch full track details for ISRC and popularity
                    try:
                        full_track = self._call_api('track', self.sp.track, track['id'])
                        isrc = full_track.get('external_ids', {}).get('isrc')
                        popularity = full_track.get('popularity', 0)

                        # Filter out tracks not by this artist (e.g., compilation albums)
                        track_artist_ids = [artist['id'] for artist in full_track.get('artists', [])]
                        if artist_id not in track_artist_ids:
                            logger.debug(
                                f"Skipping track '{track['name']}' - not by {artist_name} "
                                f"(appears on compilation)"
                            )
                            continue

                        if isrc:
                            if isrc in seen_isrcs:
                                logger.info(
                                    f"Skipped track '{track['name']}' because "
                                    f"ISRC '{isrc}' was already seen"
                                )
                                continue
                            seen_isrcs.add(isrc)

                            # Find earliest release info via ISRC search
                            earliest_date, original_album = self._get_earliest_release_info(isrc)
                            if earliest_date:
                                # Use earliest date, but still apply cutoff filter
                                if earliest_date < self.cutoff_date:
                                    logger.debug(
                                        f"Skipping track '{track['name']}' - "
                                        f"original release {earliest_date.date()} before cutoff"
                                    )
                                    continue
                                track_release_date = earliest_date
                                track_album_name = original_album or album['name']
                            else:
                                track_release_date = release_date
                                track_album_name = album['name']
                        else:
                            # No ISRC, use album release date
                            track_release_date = release_date
                            track_album_name = album['name']

                        releases.append({
                            'artist': artist_name,
                            'album': track_album_name,
                            'track': track['name'],
                            'release_date': track_release_date.strftime('%Y-%m-%d'),
                            'album_type': album['album_type'],
                            'isrc': isrc or 'N/A',
                            'spotify_url': full_track['external_urls']['spotify'],
                            'popularity': popularity,
                            # Internal IDs for caching
                            'artist_id': artist_id,
                            'album_id': album_id,
                            'track_id': track['id']
                        })

                    except Exception as e:
                        logger.warning(
                            f"Error fetching track details for '{track['name']}': {e}"
                        )
                        continue

            # Apply max_tracks cap using popularity ranking
            if max_tracks and len(releases) > max_tracks:
                logger.info(
                    f"Capping {len(releases)} releases to top {max_tracks} by popularity for '{artist_name}'"
                )
                releases.sort(key=lambda x: x['popularity'], reverse=True)
                releases = releases[:max_tracks]

            logger.info(
                f"Found {len(releases)} unique recent releases for '{artist_name}'"
            )

            # Cache the fetched releases if database is available
            if self.db and releases:
                logger.debug(f"Caching {len(releases)} releases for artist '{artist_name}'")
                for release in releases:
                    try:
                        # Extract IDs from the release data
                        # Note: We need to store artist_id, album_id, track_id which aren't in the final release dict
                        # So we need to modify the release building code to include these IDs
                        # For now, cache with what we have - we'll need to enhance this
                        cache_data = {
                            'artist_id': artist_id,
                            'album_id': release.get('album_id', ''),  # We need to add this to releases
                            'track_id': release.get('track_id', ''),  # We need to add this to releases
                            'isrc': release['isrc'] if release['isrc'] != 'N/A' else None,
                            'release_date': release['release_date'],
                            'album_name': release['album'],
                            'track_name': release['track'],
                            'album_type': release['album_type'],
                            'popularity': release['popularity'],
                            'spotify_url': release['spotify_url']
                        }
                        self.db.cache_release(cache_data)
                    except Exception as e:
                        logger.warning(f"Failed to cache release '{release['track']}': {e}")

            return releases

        except Exception as e:
            logger.error(f"Error fetching releases for '{artist_name}': {e}")
            return []


    def _process_artist(
        self,
        artist_input: str,
        max_tracks: Optional[int] = None
    ) -> Tuple[Optional[str], List[Dict]]:
        """
        Process a single artist input.

        Args:
            artist_input: Artist name or Spotify URI

        Returns:
            Tuple of (artist_name, releases_list)
        """
        artist_id, artist_name = self._parse_artist_input(artist_input)

        # Skip invalid inputs
        if not artist_id and not artist_name:
            return None, []

        # Get artist ID if we have a name
        if artist_name and not artist_id:
            artist_id, official_name = self._search_artist(artist_name)
            if not artist_id:
                return artist_name, []  # Return name for missing artists tracking

            # Update artist_name to the official one from Spotify to fix capitalization
            if official_name:
                artist_name = official_name

        # Get artist name if we have an ID
        if artist_id and not artist_name:
            artist_name = self._get_artist_name(artist_id)
            if not artist_name:
                return None, []

        # Get recent releases
        releases = self._get_recent_releases(artist_id, artist_name, max_tracks)
        return artist_name, releases

    def track_from_playlists(
        self,
        playlist_ids: List[str],
        max_tracks_per_artist: Optional[int] = None
    ) -> Dict:
        """
        Track releases from one or more playlists.

        Args:
            playlist_ids: List of Spotify playlist IDs, URIs, or URLs
            max_tracks_per_artist: Optional cap on tracks per artist

        Returns:
            Dictionary with results and statistics
        """
        logger.info(f"Tracking releases from {len(playlist_ids)} playlists...")

        all_artists_dict = {} # artist_id -> artist_name

        for playlist_id in playlist_ids:
            # Extract playlist ID from URL or URI if needed
            clean_id = playlist_id
            if 'spotify.com' in playlist_id:
                match = re.search(r'playlist/([a-zA-Z0-9]+)', playlist_id)
                if match:
                    clean_id = match.group(1)
            elif ':' in playlist_id:
                clean_id = playlist_id.split(':')[-1]

            logger.info(f"Fetching artists from playlist {clean_id}...")

            try:
                # Get playlist tracks
                results = self.sp.playlist_tracks(clean_id)
                tracks = results['items']

                # Handle pagination
                while results['next']:
                    results = self.sp.next(results)
                    tracks.extend(results['items'])

                # Extract unique artists
                for item in tracks:
                    if item.get('track') and item['track'].get('artists'):
                        for artist in item['track']['artists']:
                            artist_id = artist.get('id')
                            artist_name = artist.get('name')
                            if artist_id:
                                all_artists_dict[artist_id] = artist_name

            except Exception as e:
                logger.error(f"Error fetching playlist {clean_id}: {e}")
                # Continue with other playlists

        logger.info(f"Found {len(all_artists_dict)} unique artists across all playlists")

        return self._track_artists_common(all_artists_dict, max_tracks_per_artist)

    def track_liked_songs(
        self,
        max_tracks_per_artist: Optional[int] = None
    ) -> Dict:
        """
        Track releases from user's Liked Songs.

        Args:
            max_tracks_per_artist: Optional cap on tracks per artist

        Returns:
            Dictionary with results and statistics
        """
        logger.info("Fetching artists from Liked Songs...")

        all_artists_dict = {}

        try:
            results = self.sp.current_user_saved_tracks(limit=50)
            items = results['items']

            while results['next']:
                results = self.sp.next(results)
                items.extend(results['items'])

            for item in items:
                if item.get('track') and item['track'].get('artists'):
                    for artist in item['track']['artists']:
                        artist_id = artist.get('id')
                        artist_name = artist.get('name')
                        if artist_id:
                            all_artists_dict[artist_id] = artist_name

            logger.info(f"Found {len(all_artists_dict)} unique artists in Liked Songs")
            return self._track_artists_common(all_artists_dict, max_tracks_per_artist)

        except SpotifyException as e:
            if e.http_status == 403 or e.http_status == 401:
                return {
                    'releases': [],
                    'total_releases': 0,
                    'error': "Authentication failed for Liked Songs. Please ensure you are logged in."
                }
            raise

    def track_artist(
        self,
        artist_input: str,
        max_tracks_per_artist: Optional[int] = None
    ) -> Dict:
        """
        Track releases for a single artist.

        Args:
            artist_input: Artist name or Spotify ID
            max_tracks_per_artist: Optional cap on number of tracks per artist

        Returns:
            Dictionary with results and statistics
        """
        logger.info(f"Tracking releases for artist input '{artist_input}'...")

        try:
            artist_name, releases = self._process_artist(artist_input, max_tracks_per_artist)

            if not artist_name:
                return {
                    'releases': [],
                    'total_releases': 0,
                    'error': f"Artist '{artist_input}' not found"
                }

            # Sort releases by date (newest first)
            releases.sort(key=lambda x: x['release_date'], reverse=True)

            return {
                'releases': releases,
                'total_releases': len(releases),
                'artist_name': artist_name,
                'artist_tracked': True,
                'artists_processed': 1
            }

        except Exception as e:
            logger.error(f"Error in artist session: {e}")
            return {
                'releases': [],
                'total_releases': 0,
                'error': str(e)
            }

    def _track_artists_common(self, artists_dict: Dict[str, str], max_tracks_per_artist: Optional[int] = None) -> Dict:
        """
        Common logic to track releases for a dictionary of artists.
        """
        if not artists_dict:
            return {
                'releases': [],
                'total_releases': 0,
                'artists_processed': 0,
                'missing_artists': []
            }

        all_releases = []
        processed_count = 0
        missing_artists = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_artist = {
                executor.submit(
                    self._get_recent_releases, artist_id, artist_name, max_tracks_per_artist
                ): (artist_id, artist_name)
                for artist_id, artist_name in artists_dict.items()
            }

            with tqdm(total=len(future_to_artist), desc="Tracking artists", unit="artist") as pbar:
                for future in as_completed(future_to_artist):
                    artist_id, artist_name = future_to_artist[future]
                    try:
                        releases = future.result()
                        if releases:
                            all_releases.extend(releases)
                            processed_count += 1
                        else:
                            missing_artists.append(artist_id)
                    except Exception as e:
                        logger.error(f"Error processing artist '{artist_name}': {e}")
                    pbar.update(1)

        # Sort releases by date (newest first)
        all_releases.sort(key=lambda x: x['release_date'], reverse=True)

        return {
            'releases': all_releases,
            'total_releases': len(all_releases),
            'artists_processed': processed_count,
            'artists_in_source': len(artists_dict),
            'missing_artists': missing_artists
        }


def format_releases_tsv(releases: List[Dict]) -> str:
    """Format releases as TSV."""
    lines = []
    for release in releases:
        lines.append(
            f"{release['release_date']}\t{release['artist']}\t{release['track']}\t"
            f"{release['album']}\t{release['album_type']}\t{release['isrc']}\t{release['spotify_url']}"
        )
    return '\n'.join(lines)



def format_releases_ids(releases: List[Dict]) -> str:
    """Format releases as a list of Spotify URIs (for pasting into playlists)."""
    return '\n'.join([f"spotify:track:{r['track_id']}" for r in releases])


def format_releases_csv(releases: List[Dict]) -> str:
    """Format releases as CSV."""
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['date', 'artist', 'track', 'album', 'type', 'isrc', 'url', 'popularity'])

    for release in releases:
        writer.writerow([
            release['release_date'],
            release['artist'],
            release['track'],
            release['album'],
            release['album_type'],
            release['isrc'],
            release['spotify_url'],
            release.get('popularity', '')
        ])

    return output.getvalue().rstrip()


def format_releases_json(releases: List[Dict], meta: Dict) -> str:
    """Format releases as JSON."""
    import json
    output = {
        'releases': releases,
        'meta': meta
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def format_releases_pretty(releases: List[Dict], tracker: SpotifyReleaseTracker) -> str:
    """Format releases as pretty text (human-readable)."""
    lines = []
    lines.append("=" * 80)
    lines.append("SPOTIFY RECENT RELEASE TRACKER")
    lines.append("=" * 80)
    lines.append(f"Cutoff Date: {tracker.cutoff_date.date()} ({tracker.lookback_days} days ago)")
    lines.append(f"Total Releases Found: {len(releases)}")
    lines.append("=" * 80)
    lines.append("")

    if releases:
        for release in releases:
            lines.append(f"🎵 {release['artist']} - {release['track']}")
            lines.append(f"   Album: {release['album']} ({release['album_type']})")
            lines.append(f"   Released: {release['release_date']}")
            lines.append(f"   URL: {release['spotify_url']}")
            lines.append("")
    else:
        lines.append("No recent releases found.")
        lines.append("")

    return '\n'.join(lines)


def cmd_track(args, tracker: SpotifyReleaseTracker):
    """Handle track command."""
    
    results = {}

    if args.liked:
        # Check for redirect URI (required for OAuth)
        if not os.getenv('SPOTIPY_REDIRECT_URI'):
             # If running in a headless env without redirect URI, we can't easily do OAuth flow
             # But let's try anyway, maybe the user has a cached token
             pass

        results = tracker.track_liked_songs(args.max_per_artist)

    elif args.artist:
        results = tracker.track_artist(args.artist, args.max_per_artist)

    elif args.playlists:
        results = tracker.track_from_playlists(args.playlists, args.max_per_artist)

    else:
        # Should not happen due to argparse requirements, but safe guard
        print("Error: Please provide a playlist ID, --artist, or --liked.")
        return

    # Check for errors
    if 'error' in results:
        print(f"❌ Error: {results['error']}")
        return

    # Determine output format
    output_format = getattr(args, 'format', 'tsv')

    # Print results based on format
    if output_format == 'pretty':
        output = format_releases_pretty(results['releases'], tracker)
        print("\n" + output)

    elif output_format == 'json':
        meta = {
            'total': results['total_releases'],
            'cutoff_date': tracker.cutoff_date.date().isoformat(),
            'artists_tracked': results.get('artists_in_source', 1),
            'artists_with_releases': results.get('artists_processed', 0),
            'lookback_days': tracker.lookback_days
        }
        output = format_releases_json(results['releases'], meta)
        print(output)

    elif output_format == 'csv':
        output = format_releases_csv(results['releases'])
        print(output)

    elif output_format == 'ids':
        output = format_releases_ids(results['releases'])
        if output:
            print(output)

    else:  # tsv (default)
        output = format_releases_tsv(results['releases'])
        if output:
            print(output)

    # Print profiler summary if enabled
    if tracker.profiler:
        tracker.profiler.finish()
        print("\n", file=sys.stderr)
        print(tracker.profiler.get_summary(), file=sys.stderr)


def main():

    """Main entry point with CLI commands."""
    # Load environment variables
    load_dotenv()

    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Spotify Recent Release Tracker - Track new releases from playlists, artists, or your library',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Track from a playlist
  python main.py track 37i9dQZF1DXcBWIGoYBM5M

  # Track from multiple playlists
  python main.py track 37i9dQZF1DXcBWIGoYBM5M 4j3i...

  # Track from your "Liked Songs"
  python main.py track --liked

  # Track a single artist (demo)
  python main.py track --artist="Megadeth"

  # With options
  python main.py track 37i9dQZF1DXcBWIGoYBM5M --days 30 --format pretty
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # track command
    parser_track = subparsers.add_parser(
        'track',
        help='Track recent releases'
    )

    # Arguments for track
    parser_track.add_argument(
        'playlists',
        nargs='*',
        help='Spotify playlist IDs, URIs, or URLs'
    )

    group = parser_track.add_mutually_exclusive_group()
    group.add_argument(
        '--liked',
        action='store_true',
        help='Track from your "Liked Songs" library'
    )
    group.add_argument(
        '--artist',
        help='Track a single artist by name or ID'
    )

    parser_track.add_argument(
        '--format', '-f',
        choices=['tsv', 'json', 'csv', 'pretty', 'ids'],
        default='pretty', # Changed default to pretty for better UX as per user request
        help='Output format: pretty (default), tsv, json, or csv'
    )
    parser_track.add_argument(
        '--days', '-d',
        type=int,
        default=None,
        help='Days to look back (default: 90)'
    )
    parser_track.add_argument(
        '--since',
        type=str,
        default=None,
        help='Start date in YYYY-MM-DD format (overrides --days)'
    )
    parser_track.add_argument(
        '--max-per-artist', '-m',
        type=int,
        default=None,
        help='Cap number of tracks per artist (uses popularity ranking)'
    )
    parser_track.add_argument(
        '--profile',
        action='store_true',
        help='Enable performance profiling and show statistics'
    )
    parser_track.add_argument(
        '--force-refresh',
        action='store_true',
        help='Bypass cache and fetch fresh data from API'
    )
    parser_track.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging to console'
    )

    args = parser.parse_args()

    # Default to 'track' command and show help if no args provided
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # For 'track' command, check if any source is provided
    if args.command == 'track':
        if not args.playlists and not args.liked and not args.artist:
             # If no args provided to track, print help for track
             parser_track.print_help()
             sys.exit(0)

    # Setup logging
    setup_logging(getattr(args, 'verbose', False))

    # Check credentials
    client_id = os.getenv('SPOTIPY_CLIENT_ID')
    client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')

    if not client_id or not client_secret:
        logger.error(
            "Missing Spotify credentials. "
            "Please set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in .env file"
        )
        sys.exit(1)

    # Calculate lookback days based on arguments
    lookback_days = None
    if args.since:
        # Parse since date and calculate days
        try:
            since_date = datetime.strptime(args.since, '%Y-%m-%d')
            lookback_days = (datetime.now() - since_date).days
        except ValueError:
            logger.error(f"Invalid date format for --since: {args.since}. Use YYYY-MM-DD.")
            sys.exit(1)
    elif args.days:
        lookback_days = args.days

    # Initialize database for caching
    db = ArtistDatabase('artists.db')

    # Create profiler if --profile flag is set
    profiler = None
    if getattr(args, 'profile', False):
        profiler = PerformanceStats()

    # Determine Auth Manager
    auth_manager = None
    if getattr(args, 'liked', False):
        # Use OAuth for Liked Songs
        # Default scope for reading user library
        scope = "user-library-read"
        # If no redirect URI is set, Spotipy might warn or fail if interaction is needed
        # We assume the user has set it up or has a cached token
        redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI', 'http://localhost:8888/callback')
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            open_browser=False
        )
    else:
        # Use Client Credentials for everything else
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )

    # Initialize tracker
    tracker = SpotifyReleaseTracker(
        lookback_days=lookback_days,
        profiler=profiler,
        db=db,
        force_refresh=getattr(args, 'force_refresh', False),
        auth_manager=auth_manager
    )

    # Execute command
    if args.command == 'track':
        cmd_track(args, tracker)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
