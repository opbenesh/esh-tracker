#!/usr/bin/env python3
"""
Spotify Recent Release Tracker

Tracks recent releases (last 90 days) from a list of artists.
Uses Client Credentials Flow and ISRC-based deduplication.
Stores tracked artists in SQLite database with import from txt files or playlists.
"""

import argparse
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dotenv import load_dotenv
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials
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

    def __init__(self, client_id: str, client_secret: str, lookback_days: Optional[int] = None, profiler: Optional[PerformanceStats] = None, db: Optional[ArtistDatabase] = None, force_refresh: bool = False):
        """
        Initialize the tracker with Spotify credentials.

        Args:
            client_id: Spotify API client ID
            client_secret: Spotify API client secret
            lookback_days: Optional custom lookback window in days (default: 90)
            profiler: Optional PerformanceStats instance for profiling
            db: Optional ArtistDatabase instance for caching
            force_refresh: If True, bypass cache and fetch fresh data
        """
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

    def _search_artist(self, artist_name: str) -> Optional[str]:
        """
        Search for an artist by name and return their ID with retry logic.

        Args:
            artist_name: Name of the artist to search

        Returns:
            Artist ID or None if not found

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
                logger.info(f"Found artist '{artist['name']}' (ID: {artist_id})")
                return artist_id
            else:
                logger.warning(f"No results found for artist '{artist_name}'")
                return None

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
        # Check cache first (avoid redundant API calls within a session)
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

            # Cache the result
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
            should_stop = False

            # Process first page and check for early stopping
            for album in albums_response['items']:
                release_date = self._parse_release_date(album['release_date'])
                if not release_date:
                    continue

                # Albums are sorted by release_date DESC, so if we hit an old album, we can stop
                if release_date < self.cutoff_date:
                    logger.debug(
                        f"Hit album '{album['name']}' before cutoff ({release_date.date()}). "
                        f"Stopping pagination (smart filtering)."
                    )
                    should_stop = True
                    break

                albums_to_process.append((album, release_date))

            # Fetch remaining pages only if we haven't hit the cutoff
            while albums_response['next'] and not should_stop:
                try:
                    albums_response = self._call_api('artist_albums_next', self.sp.next, albums_response)

                    for album in albums_response['items']:
                        release_date = self._parse_release_date(album['release_date'])
                        if not release_date:
                            continue

                        if release_date < self.cutoff_date:
                            logger.debug(
                                f"Hit album '{album['name']}' before cutoff ({release_date.date()}). "
                                f"Stopping pagination (smart filtering)."
                            )
                            should_stop = True
                            break

                        albums_to_process.append((album, release_date))

                except Exception as e:
                    logger.warning(f"Error fetching next page of albums for '{artist_name}': {e}")
                    break

            logger.debug(f"Processing {len(albums_to_process)} albums for '{artist_name}' after smart filtering")

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
            artist_id = self._search_artist(artist_name)
            if not artist_id:
                return artist_name, []  # Return name for missing artists tracking

        # Get artist name if we have an ID
        if artist_id and not artist_name:
            artist_name = self._get_artist_name(artist_id)
            if not artist_name:
                return None, []

        # Get recent releases
        releases = self._get_recent_releases(artist_id, artist_name, max_tracks)
        return artist_name, releases

    def import_from_txt(
        self,
        txt_file: str,
        db: ArtistDatabase
    ) -> Tuple[int, int, List[str]]:
        """
        Import artists from a text file into the database.

        Args:
            txt_file: Path to text file containing artist names/IDs
            db: ArtistDatabase instance

        Returns:
            Tuple of (added_count, skipped_count, failed_artists)
        """
        logger.info(f"Importing artists from {txt_file}...")

        # Read artists from file
        if txt_file == '-':
            logger.info("Importing artists from stdin...")
            artist_inputs = [line.strip() for line in sys.stdin if line.strip()]
        else:
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    artist_inputs = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                logger.error(f"File '{txt_file}' not found")
                return 0, 0, []

        added = 0
        skipped = 0
        failed = []

        for artist_input in artist_inputs:
            artist_id, artist_name = self._parse_artist_input(artist_input)

            # Skip invalid inputs
            if not artist_id and not artist_name:
                continue

            # Get artist ID if we have a name
            if artist_name and not artist_id:
                artist_id = self._search_artist(artist_name)
                if not artist_id:
                    failed.append(artist_input)
                    continue

            # Get artist name if we have an ID
            if artist_id and not artist_name:
                artist_name = self._get_artist_name(artist_id)
                if not artist_name:
                    failed.append(artist_input)
                    continue

            # Add to database
            if db.add_artist(artist_name, artist_id):
                added += 1
            else:
                skipped += 1

        return added, skipped, failed

    def import_from_playlist(
        self,
        playlist_id: str,
        db: ArtistDatabase
    ) -> Tuple[int, int]:
        """
        Import all artists from a Spotify playlist into the database.

        Args:
            playlist_id: Spotify playlist ID or URI
            db: ArtistDatabase instance

        Returns:
            Tuple of (added_count, skipped_count)
        """
        logger.info(f"Importing artists from playlist {playlist_id}...")

        # Extract playlist ID from URI if needed
        if ':' in playlist_id:
            playlist_id = playlist_id.split(':')[-1]

        try:
            # Get playlist tracks
            results = self.sp.playlist_tracks(playlist_id)
            tracks = results['items']

            # Handle pagination
            while results['next']:
                results = self.sp.next(results)
                tracks.extend(results['items'])

            # Extract unique artists
            artists_dict = {}  # artist_id -> artist_name
            for item in tracks:
                if item['track'] and item['track']['artists']:
                    for artist in item['track']['artists']:
                        artist_id = artist['id']
                        artist_name = artist['name']
                        artists_dict[artist_id] = artist_name

            logger.info(f"Found {len(artists_dict)} unique artists in playlist")

            # Add to database
            artists_list = [(name, artist_id) for artist_id, name in artists_dict.items()]
            added, skipped = db.add_artists_batch(artists_list)

            return added, skipped

        except Exception as e:
            logger.error(f"Error importing from playlist: {e}")
            return 0, 0

    def track_artists_from_db(self, db: ArtistDatabase, max_per_artist: Optional[int] = None) -> Dict:
        """
        Track recent releases for all artists in the database.

        Args:
            db: ArtistDatabase instance
            max_per_artist: Optional cap on number of tracks per artist (uses popularity ranking)

        Returns:
            Dictionary with results and statistics
        """
        # Get artist IDs from database
        artist_ids = db.get_artist_ids()

        if not artist_ids:
            logger.warning("No artists in database. Use 'import-txt' or 'import-playlist' to add artists.")
            return {
                'releases': [],
                'total_releases': 0,
                'artists_processed': 0,
                'missing_artists': []
            }

        all_releases = []
        missing_artists = []
        processed_count = 0

        # Process artists concurrently with progress bar
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_id = {
                executor.submit(self._process_artist_by_id, artist_id, max_per_artist): artist_id
                for artist_id in artist_ids
            }

            # Add progress bar
            with tqdm(total=len(future_to_id), desc="Tracking artists", unit="artist") as pbar:
                for future in as_completed(future_to_id):
                    artist_id = future_to_id[future]
                    try:
                        artist_name, releases = future.result()

                        if artist_name and not releases:
                            missing_artists.append(artist_id)
                        elif releases:
                            all_releases.extend(releases)
                            processed_count += 1

                    except Exception as e:
                        logger.error(f"Error processing artist ID '{artist_id}': {e}")

                    pbar.update(1)

        # Sort releases by date (newest first)
        all_releases.sort(key=lambda x: x['release_date'], reverse=True)

        return {
            'releases': all_releases,
            'total_releases': len(all_releases),
            'artists_processed': processed_count,
            'missing_artists': missing_artists
        }

    def _process_artist_by_id(self, artist_id: str, max_tracks: Optional[int] = None) -> Tuple[Optional[str], List[Dict]]:
        """
        Process a single artist by Spotify ID.

        Args:
            artist_id: Spotify artist ID
            max_tracks: Optional cap on number of tracks to return (uses popularity ranking)

        Returns:
            Tuple of (artist_name, releases_list)
        """
        # Get artist name
        artist_name = self._get_artist_name(artist_id)
        if not artist_name:
            return None, []

        # Get recent releases
        releases = self._get_recent_releases(artist_id, artist_name, max_tracks)
        return artist_name, releases

    def track_artists(self, artists_file: str = 'artists.txt') -> Dict:
        """
        Track recent releases for all artists in the input file.

        Args:
            artists_file: Path to file containing artist names/IDs

        Returns:
            Dictionary with results and statistics
        """
        # Read artists from file
        try:
            with open(artists_file, 'r', encoding='utf-8') as f:
                artist_inputs = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            logger.error(f"Artists file '{artists_file}' not found")
            return {'error': f"File '{artists_file}' not found"}

        all_releases = []
        missing_artists = []
        processed_count = 0

        # Process artists concurrently
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_input = {
                executor.submit(self._process_artist, artist_input): artist_input
                for artist_input in artist_inputs
            }

            for future in as_completed(future_to_input):
                artist_input = future_to_input[future]
                try:
                    artist_name, releases = future.result()

                    if artist_name and not releases:
                        missing_artists.append(artist_input)
                    elif releases:
                        all_releases.extend(releases)
                        processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing '{artist_input}': {e}")

        # Sort releases by date (newest first)
        all_releases.sort(key=lambda x: x['release_date'], reverse=True)

        return {
            'releases': all_releases,
            'total_releases': len(all_releases),
            'artists_processed': processed_count,
            'missing_artists': missing_artists
        }

    def track_from_playlist_onetime(
        self,
        playlist_id: str,
        max_tracks_per_artist: Optional[int] = None
    ) -> Dict:
        """
        One-time session: Track releases from a playlist without persisting to DB.

        Args:
            playlist_id: Spotify playlist ID, URI, or URL
            max_tracks_per_artist: Optional cap on tracks per artist (uses popularity ranking)

        Returns:
            Dictionary with results and statistics
        """
        logger.info(f"One-time session: tracking releases from playlist {playlist_id}...")

        # Extract playlist ID from URL or URI if needed
        if 'spotify.com' in playlist_id:
            # Extract from URL like https://open.spotify.com/playlist/6z5jMLEBI3t9sgQ3XDKOJ0?si=...
            match = re.search(r'playlist/([a-zA-Z0-9]+)', playlist_id)
            if match:
                playlist_id = match.group(1)
        elif ':' in playlist_id:
            playlist_id = playlist_id.split(':')[-1]

        try:
            # Get playlist tracks
            results = self.sp.playlist_tracks(playlist_id)
            tracks = results['items']

            # Handle pagination
            while results['next']:
                results = self.sp.next(results)
                tracks.extend(results['items'])

            # Extract unique artists (in memory only, no DB)
            artists_dict = {}  # artist_id -> artist_name
            for item in tracks:
                if item['track'] and item['track']['artists']:
                    for artist in item['track']['artists']:
                        artist_id = artist['id']
                        artist_name = artist['name']
                        if artist_id:  # Some local files may not have IDs
                            artists_dict[artist_id] = artist_name

            logger.info(f"Found {len(artists_dict)} unique artists in playlist")

            if not artists_dict:
                return {
                    'releases': [],
                    'total_releases': 0,
                    'artists_processed': 0,
                    'missing_artists': []
                }

            # Track releases for each artist (in memory)
            all_releases = []
            processed_count = 0

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
                        except Exception as e:
                            logger.error(f"Error processing artist '{artist_name}': {e}")
                        pbar.update(1)

            # Sort releases by date (newest first)
            all_releases.sort(key=lambda x: x['release_date'], reverse=True)

            return {
                'releases': all_releases,
                'total_releases': len(all_releases),
                'artists_processed': processed_count,
                'artists_in_playlist': len(artists_dict)
            }


        except Exception as e:
            logger.error(f"Error in one-time playlist session: {e}")
            return {
                'releases': [],
                'total_releases': 0,
                'artists_processed': 0,
                'error': str(e)
            }

    def track_artist_onetime(
        self,
        artist_input: str,
        max_tracks: Optional[int] = None
    ) -> Dict:
        """
        One-time session: Track releases for a specific artist without persisting to DB.

        Args:
            artist_input: Artist name or Spotify ID
            max_tracks: Optional cap on number of tracks to return

        Returns:
            Dictionary with results and statistics
        """
        logger.info(f"One-time session: tracking releases for artist input '{artist_input}'...")

        try:
            artist_name, releases = self._process_artist(artist_input, max_tracks)

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
                'artist_tracked': True
            }

        except Exception as e:
            logger.error(f"Error in one-time artist session: {e}")
            return {
                'releases': [],
                'total_releases': 0,
                'error': str(e)
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


def format_releases_table(releases: List[Dict], tracker: SpotifyReleaseTracker, db: ArtistDatabase) -> str:
    """Format releases as pretty table (human-readable)."""
    lines = []
    lines.append("=" * 80)
    lines.append("SPOTIFY RECENT RELEASE TRACKER")
    lines.append("=" * 80)
    lines.append(f"Cutoff Date: {tracker.cutoff_date.date()} ({tracker.lookback_days} days ago)")
    lines.append(f"Total Artists in DB: {db.get_artist_count()}")
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


def cmd_import_txt(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):

    """Handle import-txt command with error handling."""
    try:
        added, skipped, failed = tracker.import_from_txt(args.file, db)

        # Output result summary to stderr to keep stdout clean for piping
        sys.stderr.write(f"Added: {added}, Skipped: {skipped}\n")
        
        if failed:
            sys.stderr.write(f"Failed to import {len(failed)} artists:\n")
            for artist in failed:
                sys.stderr.write(f"  - {artist}\n")
        
        sys.stderr.write(f"Total artists: {db.get_artist_count()}\n")

    except FileNotFoundError:
        logger.error(f"File not found: {args.file}")
        print(f"\n❌ Error: File '{args.file}' not found.")
        print("Please check the file path and try again.\n")
        sys.exit(1)
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        print(f"\n❌ Validation Error: {e}\n")
        sys.exit(1)
    except (RateLimitError, SpotifyAPIError) as e:
        logger.error(f"Spotify API error: {e}")
        print(f"\n❌ Spotify API Error: {e}")
        print("Please try again later.\n")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during import: {e}", exc_info=True)
        print(f"\n❌ Unexpected Error: {e}")
        print("Check app.log for details.\n")
        sys.exit(1)


def cmd_import_playlist(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle import-playlist command with error handling."""
    try:
        added, skipped = tracker.import_from_playlist(args.playlist, db)

        print("\n" + "="*80)
        print("IMPORT FROM SPOTIFY PLAYLIST")
        print("="*80)
        print(f"Added: {added} artists")
        print(f"Skipped (already exists): {skipped} artists")
        print(f"\nTotal artists in database: {db.get_artist_count()}")
        print("="*80 + "\n")

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        print(f"\n❌ Validation Error: {e}\n")
        sys.exit(1)
    except PlaylistNotFoundError as e:
        logger.error(f"Playlist not found: {e}")
        print(f"\n❌ Error: {e}")
        print("Please check the playlist ID or URI and try again.\n")
        sys.exit(1)
    except (RateLimitError, SpotifyAPIError) as e:
        logger.error(f"Spotify API error: {e}")
        print(f"\n❌ Spotify API Error: {e}")
        print("Please try again later.\n")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during playlist import: {e}", exc_info=True)
        print(f"\n❌ Unexpected Error: {e}")
        print("Check app.log for details.\n")
        sys.exit(1)


def cmd_list(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle list command."""
    artists = db.get_all_artists()

    print("\n" + "="*80)
    print("TRACKED ARTISTS")
    print("="*80)

    if not artists:
        print("No artists in database.")
        print("\nUse 'import-txt' or 'import-playlist' to add artists.")
    else:
        print(f"Total: {len(artists)} artists\n")
        for db_id, date_added, artist_name, spotify_id in artists:
            # Parse date
            date_obj = datetime.fromisoformat(date_added)
            date_str = date_obj.strftime("%Y-%m-%d %H:%M")
            print(f"  {artist_name}")
            print(f"    Added: {date_str}")
            print(f"    Spotify ID: {spotify_id}")
            print()

    print("="*80 + "\n")


def cmd_track(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle track command."""
    # Handle single artist preview (bypass DB)
    preview_artist = getattr(args, 'preview_artist', None)
    if preview_artist:
        # Get max_per_artist if specified
        max_per_artist = getattr(args, 'max_per_artist', None)
        results = tracker.track_artist_onetime(preview_artist, max_per_artist)
        
        # Add metadata for output formatters
        if 'error' not in results:
            results['artists_processed'] = 1 if results.get('artist_tracked') else 0
            results['missing_artists'] = []
            results['total_releases'] = len(results['releases'])
        else:
             print(f"❌ Error: {results['error']}")
             return
    
    else:
        logger.info("Starting artist tracking from database...")

        # Get max_per_artist if specified
        max_per_artist = getattr(args, 'max_per_artist', None)
        results = tracker.track_artists_from_db(db, max_per_artist=max_per_artist)

    # Determine output format
    output_format = getattr(args, 'format', 'tsv')

    # Handle legacy --pretty flag (maps to table format)
    if getattr(args, 'pretty', False):
        output_format = 'table'

    # Print results based on format
    if output_format == 'table':
        output = format_releases_table(results['releases'], tracker, db)
        print("\n" + output)

        if results['missing_artists']:
            print("="*80)
            print("⚠️  ARTISTS WITH NO RECENT RELEASES")
            print("="*80)
            for artist_id in results['missing_artists']:
                artist_info = db.get_artist_by_id(artist_id)
                if artist_info:
                    print(f"  - {artist_info[2]} (ID: {artist_id})")
            print()

    elif output_format == 'json':
        meta = {
            'total': results['total_releases'],
            'cutoff_date': tracker.cutoff_date.date().isoformat(),
            'artists_tracked': db.get_artist_count(),
            'artists_with_releases': results['artists_processed'],
            'lookback_days': tracker.lookback_days
        }
        output = format_releases_json(results['releases'], meta)
        print(output)

    elif output_format == 'csv':
        output = format_releases_csv(results['releases'])
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


def cmd_export(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle export command."""
    try:
        count = db.export_to_json(args.output)

        print("\n" + "="*80)
        print("DATABASE EXPORT")
        print("="*80)
        print(f"Successfully exported {count} artists to '{args.output}'")
        print("="*80 + "\n")

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        print(f"\n❌ Export Error: {e}")
        print("Check app.log for details.\n")
        sys.exit(1)


def cmd_import_json(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle import-json command."""
    try:
        added, skipped = db.import_from_json(args.file)

        print("\n" + "="*80)
        print("IMPORT FROM JSON BACKUP")
        print("="*80)
        print(f"Added: {added} artists")
        print(f"Skipped (already exists): {skipped} artists")
        print(f"\nTotal artists in database: {db.get_artist_count()}")
        print("="*80 + "\n")

    except FileNotFoundError:
        logger.error(f"File not found: {args.file}")
        print(f"\n❌ Error: File '{args.file}' not found.")
        print("Please check the file path and try again.\n")
        sys.exit(1)
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        print(f"\n❌ Validation Error: {e}\n")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        print(f"\n❌ Import Error: {e}")
        print("Check app.log for details.\n")
        sys.exit(1)


def cmd_remove(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle remove command."""
    try:
        # Try to remove by Spotify ID first
        if db.remove_artist(args.identifier):
            print("\n" + "="*80)
            print("ARTIST REMOVED")
            print("="*80)
            print(f"Successfully removed artist with ID: {args.identifier}")
            print(f"\nTotal artists in database: {db.get_artist_count()}")
            print("="*80 + "\n")
        else:
            # Not found by ID, search by name
            artists = db.get_all_artists()
            found = None
            for db_id, date_added, artist_name, spotify_id in artists:
                if artist_name.lower() == args.identifier.lower():
                    found = (artist_name, spotify_id)
                    break

            if found:
                artist_name, spotify_id = found
                db.remove_artist(spotify_id)
                print("\n" + "="*80)
                print("ARTIST REMOVED")
                print("="*80)
                print(f"Successfully removed: {artist_name}")
                print(f"Spotify ID: {spotify_id}")
                print(f"\nTotal artists in database: {db.get_artist_count()}")
                print("="*80 + "\n")
            else:
                print("\n" + "="*80)
                print("ARTIST NOT FOUND")
                print("="*80)
                print(f"No artist found with ID or name: {args.identifier}")
                print("\nUse 'list' command to see all tracked artists.")
                print("="*80 + "\n")

    except Exception as e:
        logger.error(f"Remove failed: {e}", exc_info=True)
        print(f"\n❌ Remove Error: {e}")
        print("Check app.log for details.\n")
        sys.exit(1)


def cmd_stats(args, tracker: SpotifyReleaseTracker, db: ArtistDatabase):
    """Handle stats command - show database statistics."""
    artists = db.get_all_artists()
    total_count = len(artists)

    print("\n" + "="*80)
    print("DATABASE STATISTICS")
    print("="*80)
    print(f"Total Artists Tracked: {total_count}")
    print(f"Lookback Window: {tracker.lookback_days} days")
    print(f"Cutoff Date: {tracker.cutoff_date.date()}")
    print(f"Database File: {db.db_path}")

    if artists:
        # Find most recently added
        most_recent = artists[0]  # Already sorted by date_added DESC
        date_obj = datetime.fromisoformat(most_recent[1])
        print(f"\nMost Recently Added: {most_recent[2]}")
        print(f"  Added: {date_obj.strftime('%Y-%m-%d %H:%M')}")

        # Find oldest
        oldest = artists[-1]
        date_obj = datetime.fromisoformat(oldest[1])
        print(f"\nOldest Entry: {oldest[2]}")
        print(f"  Added: {date_obj.strftime('%Y-%m-%d %H:%M')}")

    print("="*80 + "\n")


def cmd_preview(args, tracker: SpotifyReleaseTracker):
    """Handle preview command (one-time session, no DB persistence)."""
    try:
        max_per_artist = getattr(args, 'max_per_artist', None)
        results = tracker.track_from_playlist_onetime(args.playlist, max_per_artist)

        print("\n" + "="*80)
        print("ONE-TIME PLAYLIST SESSION (No data stored)")
        print("="*80)
        
        if 'error' in results:
            print(f"❌ Error: {results['error']}")
            print("="*80 + "\n")
            return

        print(f"Artists in Playlist: {results.get('artists_in_playlist', 0)}")
        print(f"Artists with Releases: {results['artists_processed']}")
        print(f"Total Releases Found: {results['total_releases']}")
        if max_per_artist:
            print(f"Max Tracks per Artist: {max_per_artist}")
        print("="*80 + "\n")

        # Print releases
        if results['releases']:
            for release in results['releases']:
                print(f"🎵 {release['artist']} - {release['track']}")
                print(f"   Album: {release['album']} ({release['album_type']})")
                print(f"   Released: {release['release_date']}")
                print(f"   URL: {release['spotify_url']}")
                print()
        else:
            print("No recent releases found.\n")

    except Exception as e:
        logger.error(f"Debug playlist failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        print("Check app.log for details.\n")


def main():

    """Main entry point with CLI commands."""
    # Load environment variables
    load_dotenv()

    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Spotify Recent Release Tracker - Track new releases from your favorite artists',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import artists from a text file
  python spotify_tracker.py import-txt artists.txt

  # Import artists from a Spotify playlist
  python spotify_tracker.py import-playlist 37i9dQZF1DXcBWIGoYBM5M

  # Import artists from JSON backup
  python spotify_tracker.py import-json artists_backup.json

  # List all tracked artists
  python spotify_tracker.py list

  # Track recent releases (default command)
  python spotify_tracker.py track
  python spotify_tracker.py

  # Export database to JSON backup
  python spotify_tracker.py export
  python spotify_tracker.py export my_backup.json

  # Remove an artist by name or Spotify ID
  python spotify_tracker.py remove "Taylor Swift"
  python spotify_tracker.py remove 06HL4z0CvFAxyc27GXpf02
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # import-txt command
    parser_import_txt = subparsers.add_parser(
        'import-txt',
        help='Import artists from a text file'
    )
    parser_import_txt.add_argument(
        'file',
        help='Path to text file containing artist names or Spotify URIs'
    )

    # import-playlist command
    parser_import_playlist = subparsers.add_parser(
        'import-playlist',
        help='Import artists from a Spotify playlist'
    )
    parser_import_playlist.add_argument(
        'playlist',
        help='Spotify playlist ID or URI'
    )

    # list command
    parser_list = subparsers.add_parser(
        'list',
        help='List all tracked artists'
    )

    # track command
    parser_track = subparsers.add_parser(
        'track',
        help='Track recent releases from database (default)'
    )
    parser_track.add_argument(
        '--format', '-f',
        choices=['tsv', 'json', 'csv', 'table'],
        default='tsv',
        help='Output format: tsv (default), json, csv, or table (human-readable)'
    )
    parser_track.add_argument(
        '--pretty', '-p',
        action='store_true',
        help='Use table format for human readability (legacy, use --format table instead)'
    )
    parser_track.add_argument(
        '--preview-artist', '--artist',
        dest='preview_artist',
        default=None,
        help='Preview releases for a single artist without adding to database'
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

    # export command
    parser_export = subparsers.add_parser(
        'export',
        help='Export database to JSON backup'
    )
    parser_export.add_argument(
        'output',
        nargs='?',
        default='artists_backup.json',
        help='Output JSON file path (default: artists_backup.json)'
    )

    # import-json command
    parser_import_json = subparsers.add_parser(
        'import-json',
        help='Import artists from JSON backup'
    )
    parser_import_json.add_argument(
        'file',
        help='Path to JSON backup file'
    )

    # remove command
    parser_remove = subparsers.add_parser(
        'remove',
        help='Remove an artist from database'
    )
    parser_remove.add_argument(
        'identifier',
        help='Artist name or Spotify ID to remove'
    )

    # stats command
    parser_stats = subparsers.add_parser(
        'stats',
        help='Show database statistics and overview'
    )

    # preview command (one-time session)
    parser_preview = subparsers.add_parser(
        'preview',
        help='One-time session: track releases from a playlist without storing to DB'
    )
    parser_preview.add_argument(
        'playlist',
        help='Spotify playlist ID, URI, or URL'
    )
    parser_preview.add_argument(
        '--max-per-artist', '-m',
        type=int,
        default=None,
        help='Cap number of tracks per artist (uses popularity ranking)'
    )

    # Keep debug-playlist as alias for backwards compatibility
    parser_debug_playlist = subparsers.add_parser(
        'debug-playlist',
        help='Deprecated: Use "preview" instead'
    )
    parser_debug_playlist.add_argument(
        'playlist',
        help='Spotify playlist ID, URI, or URL'
    )
    parser_debug_playlist.add_argument(
        '--max-per-artist', '-m',
        type=int,
        default=None,
        help='Cap number of tracks per artist (uses popularity ranking)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging to console'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Default to 'track' command if none specified
    if not args.command:
        args.command = 'track'

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
    if args.command == 'track':
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

    # Initialize database first
    db = ArtistDatabase('artists.db')

    # Create profiler if --profile flag is set for track command
    profiler = None
    if args.command == 'track' and getattr(args, 'profile', False):
        profiler = PerformanceStats()

    # Get force_refresh flag for track command
    force_refresh = False
    if args.command == 'track':
        force_refresh = getattr(args, 'force_refresh', False)

    # Initialize tracker with database and options
    tracker = SpotifyReleaseTracker(
        client_id,
        client_secret,
        lookback_days=lookback_days,
        profiler=profiler,
        db=db,
        force_refresh=force_refresh
    )

    # Execute command
    if args.command == 'import-txt':
        cmd_import_txt(args, tracker, db)
    elif args.command == 'import-playlist':
        cmd_import_playlist(args, tracker, db)
    elif args.command == 'import-json':
        cmd_import_json(args, tracker, db)
    elif args.command == 'list':
        cmd_list(args, tracker, db)
    elif args.command == 'track':
        cmd_track(args, tracker, db)
    elif args.command == 'export':
        cmd_export(args, tracker, db)
    elif args.command == 'remove':
        cmd_remove(args, tracker, db)
    elif args.command == 'stats':
        cmd_stats(args, tracker, db)
    elif args.command == 'preview':
        cmd_preview(args, tracker)
    elif args.command == 'debug-playlist':
        # Legacy alias - show deprecation warning
        sys.stderr.write("Warning: 'debug-playlist' is deprecated. Use 'preview' instead.\n")
        cmd_preview(args, tracker)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
