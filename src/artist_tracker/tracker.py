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


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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

    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize the tracker with Spotify credentials.

        Args:
            client_id: Spotify API client ID
            client_secret: Spotify API client secret
        """
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
        self.cutoff_date = datetime.now() - timedelta(days=self.LOOKBACK_DAYS)
        logger.info(f"Initialized tracker with cutoff date: {self.cutoff_date.date()}")

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
            return self.sp.search(
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
            artist = self.sp.artist(artist_id)
            return artist['name']
        except Exception as e:
            logger.error(f"Error fetching artist ID '{artist_id}': {e}")
            return None

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
        seen_isrcs: Set[str] = set()
        releases = []

        try:
            # Get all album types
            albums = self.sp.artist_albums(
                artist_id,
                album_type='album,single,compilation',
                limit=50
            )

            for album in albums['items']:
                # Parse release date
                release_date = self._parse_release_date(album['release_date'])
                if not release_date:
                    continue

                # Check if within lookback window
                if release_date < self.cutoff_date:
                    logger.debug(
                        f"Skipping '{album['name']}' - released {release_date.date()} "
                        f"(before cutoff {self.cutoff_date.date()})"
                    )
                    continue

                # Check for noise in album title
                if self._is_noise(album['name']):
                    logger.info(
                        f"Skipping '{album['name']}' - contains noise keyword"
                    )
                    continue

                # Get tracks from album
                album_id = album['id']
                tracks_response = self.sp.album_tracks(album_id)
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
                        full_track = self.sp.track(track['id'])
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

                        releases.append({
                            'artist': artist_name,
                            'album': album['name'],
                            'track': track['name'],
                            'release_date': release_date.strftime('%Y-%m-%d'),
                            'album_type': album['album_type'],
                            'isrc': isrc or 'N/A',
                            'spotify_url': full_track['external_urls']['spotify'],
                            'popularity': popularity
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
            return releases

        except Exception as e:
            logger.error(f"Error fetching releases for '{artist_name}': {e}")
            return []


    def _process_artist(
        self,
        artist_input: str
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
        releases = self._get_recent_releases(artist_id, artist_name)
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

    def track_artists_from_db(self, db: ArtistDatabase) -> Dict:
        """
        Track recent releases for all artists in the database.

        Args:
            db: ArtistDatabase instance

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
                executor.submit(self._process_artist_by_id, artist_id): artist_id
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

    def _process_artist_by_id(self, artist_id: str) -> Tuple[Optional[str], List[Dict]]:
        """
        Process a single artist by Spotify ID.

        Args:
            artist_id: Spotify artist ID

        Returns:
            Tuple of (artist_name, releases_list)
        """
        # Get artist name
        artist_name = self._get_artist_name(artist_id)
        if not artist_name:
            return None, []

        # Get recent releases
        releases = self._get_recent_releases(artist_id, artist_name)
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
    logger.info("Starting artist tracking from database...")
    results = tracker.track_artists_from_db(db)

    # Print results
    print("\n" + "="*80)
    print("SPOTIFY RECENT RELEASE TRACKER")
    print("="*80)
    print(f"Cutoff Date: {tracker.cutoff_date.date()} ({tracker.LOOKBACK_DAYS} days ago)")
    print(f"Total Artists in DB: {db.get_artist_count()}")
    print(f"Total Releases Found: {results['total_releases']}")
    print(f"Artists with Releases: {results['artists_processed']}")
    print("="*80 + "\n")

    # Print releases
    if results['releases']:
        for release in results['releases']:
            print(f"🎵 {release['artist']} - {release['track']}")
            print(f"   Album: {release['album']} ({release['album_type']})")
            print(f"   Released: {release['release_date']}")
            print(f"   ISRC: {release['isrc']}")
            print(f"   URL: {release['spotify_url']}")
            print()
    else:
        print("No recent releases found.\n")

    # Print missing artists
    if results['missing_artists']:
        print("="*80)
        print("⚠️  ARTISTS WITH NO RECENT RELEASES")
        print("="*80)
        for artist_id in results['missing_artists']:
            artist_info = db.get_artist_by_id(artist_id)
            if artist_info:
                print(f"  - {artist_info[2]} (ID: {artist_id})")
        print()


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


def cmd_debug_playlist(args, tracker: SpotifyReleaseTracker):
    """Handle debug-playlist command (one-time session, no DB persistence)."""
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
                popularity_str = f" (pop: {release.get('popularity', 'N/A')})"
                print(f"🎵 {release['artist']} - {release['track']}{popularity_str}")
                print(f"   Album: {release['album']} ({release['album_type']})")
                print(f"   Released: {release['release_date']}")
                print(f"   ISRC: {release['isrc']}")
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

    # debug-playlist command (one-time session)
    parser_debug_playlist = subparsers.add_parser(
        'debug-playlist',
        help='One-time session: track releases from a playlist without storing to DB'
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

    args = parser.parse_args()

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

    # Initialize tracker and database
    tracker = SpotifyReleaseTracker(client_id, client_secret)
    db = ArtistDatabase('artists.db')

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
    elif args.command == 'debug-playlist':
        cmd_debug_playlist(args, tracker)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
