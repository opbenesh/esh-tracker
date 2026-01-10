#!/usr/bin/env python3
"""
Benchmark Suite for Spotify Release Tracker

Ensures reproducible performance measurements across machines and time by:
1. Using fixed artist IDs (no search API variation)
2. Using fixed cutoff dates in the past (immutable release data)
3. Measuring API calls as primary metric (network-independent)
4. Testing both cold cache (fresh DB) and hot cache (warm DB) scenarios
5. Using cassette recording to minimize actual Spotify API calls

Usage:
    # Standard mode (uses cassettes, no API calls)
    python benchmarks/benchmark.py --suite small

    # Record mode (makes real API calls, updates cassettes)
    BENCHMARK_RECORD=1 python benchmarks/benchmark.py --suite small

    # Save results
    python benchmarks/benchmark.py --suite all --output results/benchmark_$(date +%Y%m%d_%H%M%S).json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import re


class BenchmarkRunner:
    """Manages benchmark execution and result collection"""

    def __init__(self, project_root: Path, use_cassettes: bool = True):
        self.project_root = project_root
        self.fixtures_dir = project_root / "benchmarks" / "fixtures"
        self.results_dir = project_root / "benchmarks" / "results"
        self.cassettes_dir = project_root / "benchmarks" / "cassettes"
        self.db_path = project_root / "artists.db"
        self.main_script = project_root / "main.py"
        self.use_cassettes = use_cassettes

        # Ensure directories exist
        self.results_dir.mkdir(parents=True, exist_ok=True)
        if use_cassettes:
            self.cassettes_dir.mkdir(parents=True, exist_ok=True)

        # Add src to path for imports
        sys.path.insert(0, str(project_root / "src"))

    def load_fixture(self, fixture_name: str) -> Dict[str, Any]:
        """Load artist fixture from JSON file"""
        fixture_path = self.fixtures_dir / f"{fixture_name}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")

        with open(fixture_path, 'r') as f:
            return json.load(f)

    def setup_database(self, fixture_data: Dict[str, Any]) -> None:
        """Populate database with artists from fixture"""
        # Remove existing database for clean state
        if self.db_path.exists():
            self.db_path.unlink()

        # Import artists using their IDs (no search needed)
        # Create temporary file with artist IDs
        import_file = self.project_root / "temp_import.txt"
        try:
            with open(import_file, 'w') as f:
                for artist in fixture_data['artists']:
                    # Use spotify:artist:ID format to skip search
                    f.write(f"spotify:artist:{artist['id']}\n")

            # Import artists
            cmd = [
                sys.executable,
                str(self.main_script),
                "import-txt",
                str(import_file)
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to import artists: {result.stderr}")

        finally:
            if import_file.exists():
                import_file.unlink()

    def parse_profile_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """Extract performance metrics from profile output"""
        # Profile stats are printed to stderr
        output = stderr

        metrics = {
            "api_calls": {},
            "api_calls_total": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_hit_rate": 0.0,
            "execution_time_seconds": 0.0,
            "releases_found": 0
        }

        # Extract API calls
        # Format: "  - artist_albums: 20"
        api_call_pattern = r'^\s*-\s*(\w+):\s*(\d+)'
        in_api_section = False

        for line in output.split('\n'):
            line = line.strip()

            # Detect sections
            if 'API Calls:' in line:
                in_api_section = True
                # Extract total from "API Calls: 45 total"
                total_match = re.search(r'API Calls:\s*(\d+)\s*total', line)
                if total_match:
                    metrics['api_calls_total'] = int(total_match.group(1))
                continue

            if 'Cache Statistics:' in line:
                in_api_section = False
                continue

            # Parse API call breakdown
            if in_api_section:
                match = re.match(api_call_pattern, line)
                if match:
                    endpoint = match.group(1)
                    count = int(match.group(2))
                    metrics['api_calls'][endpoint] = count

            # Parse cache statistics
            if 'Hits:' in line:
                match = re.search(r'Hits:\s*(\d+)', line)
                if match:
                    metrics['cache_hits'] = int(match.group(1))

            if 'Misses:' in line:
                match = re.search(r'Misses:\s*(\d+)', line)
                if match:
                    metrics['cache_misses'] = int(match.group(1))

            if 'Hit Rate:' in line:
                match = re.search(r'Hit Rate:\s*([\d.]+)%', line)
                if match:
                    metrics['cache_hit_rate'] = float(match.group(1))

            # Parse duration
            if 'Total Duration:' in line:
                match = re.search(r'Total Duration:\s*([\d.]+)s', line)
                if match:
                    metrics['execution_time_seconds'] = float(match.group(1))

        # Count releases from stdout (TSV output)
        # Skip header line, count remaining lines
        lines = [l for l in stdout.strip().split('\n') if l]
        if lines:
            metrics['releases_found'] = max(0, len(lines) - 1)  # Subtract header

        return metrics

    def run_track_command(self, cutoff_date: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Run the track command with profiling enabled"""
        cmd = [
            sys.executable,
            str(self.main_script),
            "track",
            "--since", cutoff_date,
            "--profile",
            "--format", "tsv"
        ]

        if force_refresh:
            cmd.append("--force-refresh")

        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.project_root
        )
        end_time = time.time()

        if result.returncode != 0:
            raise RuntimeError(f"Track command failed: {result.stderr}")

        metrics = self.parse_profile_output(result.stdout, result.stderr)
        metrics['wall_time_seconds'] = end_time - start_time

        return metrics

    def run_track_with_cassette(self, cassette_name: str, cutoff_date: str,
                                artist_ids: List[str]) -> Dict[str, Any]:
        """
        Run track command directly using tracker API with cassette support

        Args:
            cassette_name: Name for cassette file
            cutoff_date: Cutoff date string (YYYY-MM-DD)
            artist_ids: List of Spotify artist IDs

        Returns:
            Metrics dictionary
        """
        from dotenv import load_dotenv
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        from artist_tracker.tracker import SpotifyReleaseTracker
        from artist_tracker.database import ArtistDatabase
        from artist_tracker.profiler import PerformanceStats
        from benchmarks.cassette import create_mock_spotify

        # Load credentials
        load_dotenv(self.project_root / ".env")
        client_id = os.environ.get('SPOTIFY_CLIENT_ID', 'dummy_id')
        client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET', 'dummy_secret')

        # Create real Spotify client
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        real_client = spotipy.Spotify(auth_manager=auth_manager)

        # Wrap with cassette mock
        mock_client = create_mock_spotify(real_client, cassette_name, self.cassettes_dir)

        # Setup profiler and database
        profiler = PerformanceStats()
        db = ArtistDatabase(str(self.db_path))

        # Calculate lookback days from cutoff date
        cutoff_datetime = datetime.strptime(cutoff_date, "%Y-%m-%d")
        lookback_days = (datetime.now() - cutoff_datetime).days

        # Create tracker with mock client
        tracker = SpotifyReleaseTracker(
            client_id=client_id,
            client_secret=client_secret,
            lookback_days=lookback_days,
            profiler=profiler,
            db=db,
            spotify_client=mock_client
        )

        # Run tracking
        start_time = time.time()

        try:
            # Track releases by artist IDs
            releases = []
            for artist_id in artist_ids:
                artist_releases = tracker._get_recent_releases(artist_id)
                releases.extend(artist_releases)

            execution_time = time.time() - start_time

            # Finalize cassette
            mock_client.finalize_cassette()

            # Build metrics from profiler
            metrics = {
                "api_calls_total": profiler.get_total_api_calls(),
                "api_calls": profiler.api_calls.copy(),
                "cache_hits": profiler.cache_hits,
                "cache_misses": profiler.cache_misses,
                "cache_hit_rate": profiler.get_cache_hit_rate(),
                "execution_time_seconds": execution_time,
                "releases_found": len(releases),
                "wall_time_seconds": execution_time
            }

            return metrics

        finally:
            # Always finalize cassette
            mock_client.finalize_cassette()

    def run_scenario(self, scenario_name: str, fixture_data: Dict[str, Any],
                     cold_cache: bool) -> Dict[str, Any]:
        """Run a single benchmark scenario"""
        print(f"\n{'='*80}")
        print(f"Running: {scenario_name}")
        print(f"Cache mode: {'COLD' if cold_cache else 'HOT'}")
        print(f"Artists: {len(fixture_data['artists'])}")
        print(f"Cutoff date: {fixture_data['cutoff_date']}")
        if self.use_cassettes:
            cassette_mode = "RECORD" if os.environ.get('BENCHMARK_RECORD') else "PLAYBACK"
            print(f"Cassette mode: {cassette_mode}")
        print(f"{'='*80}")

        # Setup database (creates clean state for cold cache)
        if cold_cache:
            print("Setting up fresh database...")
            self.setup_database(fixture_data)

        # Run benchmark
        print("Executing track command...")

        if self.use_cassettes:
            # Use cassette mode (minimal API calls)
            artist_ids = [artist['id'] for artist in fixture_data['artists']]
            cassette_name = f"{scenario_name}"
            metrics = self.run_track_with_cassette(
                cassette_name=cassette_name,
                cutoff_date=fixture_data['cutoff_date'],
                artist_ids=artist_ids
            )
        else:
            # Use subprocess mode (runs actual CLI)
            metrics = self.run_track_command(
                cutoff_date=fixture_data['cutoff_date'],
                force_refresh=False  # We control cache via DB state
            )

        # Build result
        result = {
            "scenario": scenario_name,
            "fixture": fixture_data.get('description', ''),
            "cache_mode": "cold" if cold_cache else "hot",
            "artist_count": len(fixture_data['artists']),
            "cutoff_date": fixture_data['cutoff_date'],
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "metrics": metrics
        }

        # Print summary
        print(f"\nResults:")
        print(f"  API Calls: {metrics['api_calls_total']}")
        print(f"  Cache Hit Rate: {metrics['cache_hit_rate']:.1f}%")
        print(f"  Execution Time: {metrics['execution_time_seconds']:.2f}s")
        print(f"  Releases Found: {metrics['releases_found']}")

        return result

    def run_suite(self, suite_name: str) -> List[Dict[str, Any]]:
        """Run a benchmark suite (small, medium, large, or all)"""
        results = []

        if suite_name == "all":
            suites = ["artists_small", "artists_medium", "artists_large"]
        else:
            suites = [f"artists_{suite_name}"]

        for fixture_name in suites:
            try:
                fixture_data = self.load_fixture(fixture_name)
            except FileNotFoundError:
                print(f"Warning: Fixture {fixture_name} not found, skipping...")
                continue

            # Run cold cache scenario
            result_cold = self.run_scenario(
                scenario_name=f"{fixture_name}_cold",
                fixture_data=fixture_data,
                cold_cache=True
            )
            results.append(result_cold)

            # Run hot cache scenario (immediately after cold, so cache is warm)
            result_hot = self.run_scenario(
                scenario_name=f"{fixture_name}_hot",
                fixture_data=fixture_data,
                cold_cache=False
            )
            results.append(result_hot)

        return results

    def save_results(self, results: List[Dict[str, Any]], output_path: Path) -> None:
        """Save benchmark results to JSON file"""
        output = {
            "benchmark_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "environment": {
                "python_version": sys.version,
                "platform": sys.platform
            },
            "results": results
        }

        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n{'='*80}")
        print(f"Results saved to: {output_path}")
        print(f"{'='*80}")

    def print_summary(self, results: List[Dict[str, Any]]) -> None:
        """Print a summary comparison of results"""
        print(f"\n{'='*80}")
        print("BENCHMARK SUMMARY")
        print(f"{'='*80}\n")

        # Group by fixture
        by_fixture = {}
        for result in results:
            fixture = result['scenario'].rsplit('_', 1)[0]  # Remove _cold/_hot suffix
            if fixture not in by_fixture:
                by_fixture[fixture] = {}
            cache_mode = result['cache_mode']
            by_fixture[fixture][cache_mode] = result

        # Print comparison
        for fixture, modes in by_fixture.items():
            print(f"\n{fixture.upper()}")
            print("-" * 80)

            if 'cold' in modes and 'hot' in modes:
                cold = modes['cold']['metrics']
                hot = modes['hot']['metrics']

                print(f"{'Metric':<30} {'Cold Cache':<15} {'Hot Cache':<15} {'Improvement':<15}")
                print("-" * 80)

                # API Calls
                cold_api = cold['api_calls_total']
                hot_api = hot['api_calls_total']
                if cold_api > 0:
                    api_reduction = ((cold_api - hot_api) / cold_api * 100)
                    print(f"{'API Calls':<30} {cold_api:<15} {hot_api:<15} {api_reduction:>13.1f}%")

                # Cache Hit Rate
                print(f"{'Cache Hit Rate':<30} {cold['cache_hit_rate']:<14.1f}% {hot['cache_hit_rate']:<14.1f}%")

                # Execution Time
                cold_time = cold['execution_time_seconds']
                hot_time = hot['execution_time_seconds']
                if cold_time > 0:
                    time_reduction = ((cold_time - hot_time) / cold_time * 100)
                    print(f"{'Execution Time (s)':<30} {cold_time:<14.2f}s {hot_time:<14.2f}s {time_reduction:>13.1f}%")

                # Releases
                print(f"{'Releases Found':<30} {cold['releases_found']:<15} {hot['releases_found']:<15}")

        print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run benchmark suite for Spotify Release Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmarks/benchmark.py --suite small
  python benchmarks/benchmark.py --suite all --output results/latest.json
  python benchmarks/benchmark.py --suite medium
        """
    )

    parser.add_argument(
        '--suite',
        choices=['small', 'medium', 'large', 'all'],
        default='small',
        help='Benchmark suite to run (default: small)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output JSON file path (default: results/benchmark_TIMESTAMP.json)'
    )

    parser.add_argument(
        '--no-cassettes',
        action='store_true',
        help='Disable cassettes and make real API calls (runs via CLI subprocess)'
    )

    args = parser.parse_args()

    # Determine project root (parent of benchmarks directory)
    project_root = Path(__file__).parent.parent

    # Initialize runner
    use_cassettes = not args.no_cassettes
    runner = BenchmarkRunner(project_root, use_cassettes=use_cassettes)

    # Run benchmarks
    print("Starting benchmark suite...")
    print(f"Suite: {args.suite}")
    print(f"Cassettes: {'enabled' if use_cassettes else 'disabled'}")
    if use_cassettes and os.environ.get('BENCHMARK_RECORD'):
        print("⚠️  RECORD MODE - Will make real API calls and update cassettes")

    results = runner.run_suite(args.suite)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = runner.results_dir / f"benchmark_{timestamp}.json"

    # Save results
    runner.save_results(results, output_path)

    # Print summary
    runner.print_summary(results)

    print("Benchmark complete!")


if __name__ == "__main__":
    main()
