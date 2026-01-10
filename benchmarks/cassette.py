#!/usr/bin/env python3
"""
Cassette Recording System for Spotify API Mocking

Implements a VCR-style recording/playback system to minimize actual API calls
during benchmarking. Records Spotify API responses to JSON files and replays
them in subsequent runs.

Usage:
    # Record mode (makes real API calls, saves responses)
    BENCHMARK_RECORD=1 python benchmarks/benchmark.py --suite small

    # Playback mode (uses cached responses, no API calls)
    python benchmarks/benchmark.py --suite small
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from collections import OrderedDict


class SpotifyCassette:
    """
    Records and replays Spotify API calls for reproducible benchmarking.

    A cassette is a JSON file containing request/response pairs. Each request
    is identified by a hash of the method name and parameters.
    """

    def __init__(self, cassette_path: Path, mode: str = "playback"):
        """
        Initialize cassette

        Args:
            cassette_path: Path to cassette JSON file
            mode: "record", "playback", or "record_once" (record if missing, else playback)
        """
        self.cassette_path = cassette_path
        self.mode = mode
        self.interactions: Dict[str, Any] = {}
        self.interaction_order: List[str] = []
        self.api_call_count = 0
        self.cache_hit_count = 0

        # Ensure directory exists
        self.cassette_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing cassette in playback mode
        if mode in ("playback", "record_once"):
            if self.cassette_path.exists():
                self._load()
                if mode == "record_once":
                    self.mode = "playback"
            elif mode == "record_once":
                self.mode = "record"

    def _load(self) -> None:
        """Load cassette from disk"""
        try:
            with open(self.cassette_path, 'r') as f:
                data = json.load(f)
                self.interactions = data.get('interactions', {})
                self.interaction_order = data.get('interaction_order', [])
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Warning: Could not load cassette {self.cassette_path}: {e}")
            self.interactions = {}
            self.interaction_order = []

    def _save(self) -> None:
        """Save cassette to disk"""
        data = {
            'version': '1.0',
            'interactions': self.interactions,
            'interaction_order': self.interaction_order,
            'metadata': {
                'total_interactions': len(self.interactions),
                'api_calls_recorded': len(self.interaction_order)
            }
        }

        with open(self.cassette_path, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)

    def _make_key(self, method: str, args: tuple, kwargs: dict) -> str:
        """
        Generate unique key for a method call

        Args:
            method: Method name (e.g., 'artist', 'search', 'artist_albums')
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Hash string identifying this unique call
        """
        # Create a deterministic representation
        key_data = {
            'method': method,
            'args': args,
            'kwargs': OrderedDict(sorted(kwargs.items()))
        }

        # Convert to JSON and hash
        key_json = json.dumps(key_data, sort_keys=True, default=str)
        key_hash = hashlib.sha256(key_json.encode()).hexdigest()[:16]

        # Human-readable prefix
        if args:
            prefix = f"{method}_{args[0]}"[:50]
        elif kwargs:
            first_val = str(list(kwargs.values())[0])[:30]
            prefix = f"{method}_{first_val}"
        else:
            prefix = method

        # Sanitize prefix
        prefix = "".join(c if c.isalnum() or c in "-_" else "_" for c in prefix)

        return f"{prefix}_{key_hash}"

    def record_call(self, method: str, args: tuple, kwargs: dict, response: Any) -> None:
        """Record an API call and its response"""
        key = self._make_key(method, args, kwargs)

        self.interactions[key] = {
            'method': method,
            'args': args,
            'kwargs': kwargs,
            'response': response
        }

        self.interaction_order.append(key)
        self.api_call_count += 1

    def playback_call(self, method: str, args: tuple, kwargs: dict) -> Optional[Any]:
        """
        Retrieve recorded response for a method call

        Returns:
            Recorded response if found, None otherwise
        """
        key = self._make_key(method, args, kwargs)

        if key in self.interactions:
            self.cache_hit_count += 1
            return self.interactions[key]['response']

        return None

    def finalize(self) -> None:
        """Save cassette if in record mode"""
        if self.mode == "record":
            self._save()
            print(f"💾 Cassette saved: {self.cassette_path}")
            print(f"   Recorded {len(self.interactions)} unique API calls")


class SpotifyMock:
    """
    Mock Spotify client that records/replays API calls via cassettes

    Acts as a transparent wrapper around spotipy.Spotify, intercepting
    method calls and routing them to cassette playback or real API.
    """

    def __init__(self, real_client, cassette: SpotifyCassette):
        """
        Initialize mock client

        Args:
            real_client: Real spotipy.Spotify instance
            cassette: Cassette for recording/playback
        """
        self._real_client = real_client
        self._cassette = cassette

        # Methods to intercept (common Spotify API calls)
        self._intercepted_methods = {
            'artist', 'artist_albums', 'album_tracks', 'track',
            'search', 'next', 'playlist_tracks', 'playlist'
        }

    def __getattr__(self, name: str):
        """
        Intercept method calls

        If method is in intercepted list, route through cassette.
        Otherwise, delegate to real client.
        """
        if name in self._intercepted_methods:
            return self._make_interceptor(name)

        # Pass through to real client
        return getattr(self._real_client, name)

    def _make_interceptor(self, method_name: str):
        """Create interceptor function for a method"""
        def interceptor(*args, **kwargs):
            # Try playback first
            if self._cassette.mode == "playback":
                response = self._cassette.playback_call(method_name, args, kwargs)
                if response is not None:
                    return response

                # Cache miss in playback mode
                raise RuntimeError(
                    f"Cassette cache miss in playback mode!\n"
                    f"Method: {method_name}\n"
                    f"Args: {args}\n"
                    f"Kwargs: {kwargs}\n\n"
                    f"This means the cassette is incomplete. Run in record mode:\n"
                    f"  BENCHMARK_RECORD=1 python benchmarks/benchmark.py --suite <name>"
                )

            # Record mode: make real API call and record
            real_method = getattr(self._real_client, method_name)
            response = real_method(*args, **kwargs)

            if self._cassette.mode == "record":
                self._cassette.record_call(method_name, args, kwargs, response)

            return response

        return interceptor

    def finalize_cassette(self) -> None:
        """Finalize cassette (save if recording)"""
        self._cassette.finalize()


def create_mock_spotify(real_client, cassette_name: str,
                        cassettes_dir: Optional[Path] = None) -> SpotifyMock:
    """
    Create a mock Spotify client with cassette recording/playback

    Args:
        real_client: Real spotipy.Spotify instance
        cassette_name: Name for the cassette file (without .json extension)
        cassettes_dir: Directory for cassettes (default: benchmarks/cassettes)

    Returns:
        SpotifyMock instance

    Environment Variables:
        BENCHMARK_RECORD: Set to "1" to enable recording mode
    """
    if cassettes_dir is None:
        cassettes_dir = Path(__file__).parent / "cassettes"

    # Determine mode from environment
    record_mode = os.environ.get('BENCHMARK_RECORD', '').lower() in ('1', 'true', 'yes')
    mode = "record" if record_mode else "record_once"

    cassette_path = cassettes_dir / f"{cassette_name}.json"
    cassette = SpotifyCassette(cassette_path, mode=mode)

    return SpotifyMock(real_client, cassette)


def get_cassette_stats(cassette_path: Path) -> Dict[str, Any]:
    """
    Get statistics about a cassette file

    Args:
        cassette_path: Path to cassette JSON file

    Returns:
        Dictionary with cassette statistics
    """
    if not cassette_path.exists():
        return {'exists': False}

    try:
        with open(cassette_path, 'r') as f:
            data = json.load(f)

        interactions = data.get('interactions', {})

        # Count by method
        method_counts = {}
        for interaction in interactions.values():
            method = interaction.get('method', 'unknown')
            method_counts[method] = method_counts.get(method, 0) + 1

        return {
            'exists': True,
            'total_interactions': len(interactions),
            'method_breakdown': method_counts,
            'version': data.get('version', 'unknown'),
            'size_bytes': cassette_path.stat().st_size
        }
    except Exception as e:
        return {
            'exists': True,
            'error': str(e)
        }


def list_cassettes(cassettes_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    List all cassettes in the cassettes directory

    Args:
        cassettes_dir: Directory to search (default: benchmarks/cassettes)

    Returns:
        List of cassette information dictionaries
    """
    if cassettes_dir is None:
        cassettes_dir = Path(__file__).parent / "cassettes"

    if not cassettes_dir.exists():
        return []

    cassettes = []
    for cassette_file in sorted(cassettes_dir.glob("*.json")):
        stats = get_cassette_stats(cassette_file)
        stats['name'] = cassette_file.stem
        stats['path'] = str(cassette_file)
        cassettes.append(stats)

    return cassettes
