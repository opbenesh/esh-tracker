#!/usr/bin/env python3
"""
Spotify Recent Release Tracker

Tracks recent releases (last 90 days) from a list of artists.
Uses Client Credentials Flow and ISRC-based deduplication.
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


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

    # Market for regional filtering
    MARKET = 'IL'

    # Lookback window in days
    LOOKBACK_DAYS = 90

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
        Search for an artist by name and return their ID.

        Args:
            artist_name: Name of the artist to search

        Returns:
            Artist ID or None if not found
        """
        try:
            results = self.sp.search(
                q=f'artist:{artist_name}',
                type='artist',
                limit=1,
                market=self.MARKET
            )

            if results['artists']['items']:
                artist = results['artists']['items'][0]
                artist_id = artist['id']
                logger.info(f"Found artist '{artist['name']}' (ID: {artist_id})")
                return artist_id
            else:
                logger.warning(f"No results found for artist '{artist_name}'")
                return None

        except Exception as e:
            logger.error(f"Error searching for artist '{artist_name}': {e}")
            return None

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
        artist_name: str
    ) -> List[Dict]:
        """
        Get recent releases for an artist.

        Args:
            artist_id: Spotify artist ID
            artist_name: Artist name for logging

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
                limit=50,
                market=self.MARKET
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
                tracks_response = self.sp.album_tracks(album_id, market=self.MARKET)
                tracks = tracks_response['items']

                for track in tracks:
                    # Check for noise in track title
                    if self._is_noise(track['name']):
                        logger.info(
                            f"Skipping track '{track['name']}' - contains noise keyword"
                        )
                        continue

                    # Get ISRC for deduplication
                    # Need to fetch full track details for ISRC
                    try:
                        full_track = self.sp.track(track['id'], market=self.MARKET)
                        isrc = full_track.get('external_ids', {}).get('isrc')

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
                            'spotify_url': full_track['external_urls']['spotify']
                        })

                    except Exception as e:
                        logger.warning(
                            f"Error fetching track details for '{track['name']}': {e}"
                        )
                        continue

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


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()

    client_id = os.getenv('SPOTIPY_CLIENT_ID')
    client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')

    if not client_id or not client_secret:
        logger.error(
            "Missing Spotify credentials. "
            "Please set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in .env file"
        )
        return

    # Initialize tracker
    tracker = SpotifyReleaseTracker(client_id, client_secret)

    # Track artists
    logger.info("Starting artist tracking...")
    results = tracker.track_artists('artists.txt')

    if 'error' in results:
        logger.error(results['error'])
        return

    # Print results
    print("\n" + "="*80)
    print(f"SPOTIFY RECENT RELEASE TRACKER")
    print("="*80)
    print(f"Cutoff Date: {tracker.cutoff_date.date()} ({tracker.LOOKBACK_DAYS} days ago)")
    print(f"Total Releases Found: {results['total_releases']}")
    print(f"Artists Processed: {results['artists_processed']}")
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
        print("⚠️  MISSING ARTISTS (no results found)")
        print("="*80)
        for artist in results['missing_artists']:
            print(f"  - {artist}")
        print("\nPlease check for typos or use Spotify artist URIs.\n")


if __name__ == '__main__':
    main()
