#!/usr/bin/env python3
"""
Weekly Run Benchmark Suite

Tests incremental mode, delta-only reporting, and activity profiling
to demonstrate 90% efficiency improvements for recurring weekly runs.

Usage:
    # Run weekly scenario benchmark
    python benchmarks/benchmark_weekly.py --suite weekly_simulation

    # Record mode (with real API calls)
    BENCHMARK_RECORD=1 python benchmarks/benchmark_weekly.py --suite weekly_simulation
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from artist_tracker.tracker import SpotifyReleaseTracker
from artist_tracker.database import ArtistDatabase
from artist_tracker.profiler import PerformanceStats
from benchmarks.cassette import create_mock_spotify
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class WeeklyBenchmarkRunner:
    """Benchmark runner for weekly run optimizations."""

    def __init__(self, project_root: Path, use_cassettes: bool = True):
        self.project_root = project_root
        self.fixtures_dir = project_root / "benchmarks" / "fixtures"
        self.results_dir = project_root / "benchmarks" / "results"
        self.cassettes_dir = project_root / "benchmarks" / "cassettes"
        self.db_path = project_root / "artists.db"
        self.use_cassettes = use_cassettes

        # Ensure directories exist
        self.results_dir.mkdir(parents=True, exist_ok=True)
        if use_cassettes:
            self.cassettes_dir.mkdir(parents=True, exist_ok=True)

    def load_fixture(self, fixture_name: str) -> Dict[str, Any]:
        """Load artist fixture from JSON file"""
        fixture_path = self.fixtures_dir / f"{fixture_name}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")

        with open(fixture_path, 'r') as f:
            return json.load(f)

    def setup_clean_database(self, fixture_data: Dict[str, Any]) -> ArtistDatabase:
        """Create a clean database with artists."""
        # Remove existing database
        if self.db_path.exists():
            self.db_path.unlink()

        db = ArtistDatabase(str(self.db_path))

        # Add artists using batch operation
        artists_to_add = [(artist['name'], artist['id']) for artist in fixture_data['artists']]
        added, skipped = db.add_artists_batch(artists_to_add)

        print(f"  Database setup: {added} artists added, {skipped} skipped")
        return db

    def run_with_tracker(self, artists: List[Dict[str, str]], cutoff_date: str,
                        incremental: bool = False, cassette_name: str = None) -> Dict[str, Any]:
        """
        Run tracking with specified configuration.

        Args:
            artists: List of artist dictionaries with 'id' and 'name'
            cutoff_date: Cutoff date for releases
            incremental: Whether to use incremental mode
            cassette_name: Name for cassette file

        Returns:
            Metrics dictionary
        """
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
        if self.use_cassettes and cassette_name:
            mock_client = create_mock_spotify(real_client, cassette_name, self.cassettes_dir)
        else:
            mock_client = real_client

        # Setup profiler and database
        profiler = PerformanceStats()
        db = ArtistDatabase(str(self.db_path))

        # Calculate lookback days from cutoff date
        cutoff_datetime = datetime.strptime(cutoff_date, "%Y-%m-%d")
        lookback_days = (datetime.now() - cutoff_datetime).days

        # Create tracker
        tracker = SpotifyReleaseTracker(
            client_id=client_id,
            client_secret=client_secret,
            lookback_days=lookback_days,
            profiler=profiler,
            db=db,
            spotify_client=mock_client,
            incremental=incremental
        )

        # Run tracking
        start_time = time.time()

        try:
            releases = []
            for artist in artists:
                artist_releases = tracker._get_recent_releases(artist['id'], artist['name'])
                releases.extend(artist_releases)

            execution_time = time.time() - start_time

            # Finalize cassette
            if self.use_cassettes and cassette_name:
                mock_client.finalize_cassette()

            # Get activity profiles
            activity_profiles = {}
            for artist in artists:
                profile = db.get_artist_activity_profile(artist['id'])
                activity_profiles[artist['id']] = profile

            # Build metrics
            metrics = {
                "api_calls_total": profiler.total_api_calls,
                "api_calls": dict(profiler.api_calls),
                "cache_hits": profiler.cache_hits,
                "cache_misses": profiler.cache_misses,
                "cache_hit_rate": profiler.cache_hit_rate,
                "execution_time_seconds": execution_time,
                "releases_found": len(releases),
                "wall_time_seconds": execution_time,
                "lookback_days": tracker.lookback_days,
                "incremental_mode": incremental,
                "activity_profiles": activity_profiles
            }

            # Record run in database for next incremental run
            db.record_run(
                artists_tracked=len(artists),
                releases_found=len(releases),
                lookback_days=tracker.lookback_days,
                duration_seconds=execution_time,
                api_calls_made=profiler.total_api_calls
            )

            return metrics

        finally:
            # Always finalize cassette
            if self.use_cassettes and cassette_name:
                mock_client.finalize_cassette()

    def run_weekly_simulation(self, fixture_name: str) -> Dict[str, Any]:
        """
        Simulate multiple weekly runs to demonstrate efficiency gains.

        Week 1: Baseline run (90 days lookback)
        Week 2: Incremental run (7 days lookback)
        Week 3: Incremental run (7 days lookback)
        Week 4: Incremental run (7 days lookback)
        """
        print("\n" + "=" * 80)
        print("WEEKLY RUN SIMULATION")
        print("=" * 80)

        fixture_data = self.load_fixture(fixture_name)
        artists = fixture_data['artists']
        cutoff_date = fixture_data['cutoff_date']

        results = {
            'fixture': fixture_name,
            'artists_count': len(artists),
            'cutoff_date': cutoff_date,
            'weeks': []
        }

        # Week 1: Baseline run (no incremental mode)
        print("\n📅 WEEK 1: Baseline Run (Full 90-day lookback)")
        print("-" * 80)
        db = self.setup_clean_database(fixture_data)

        week1_metrics = self.run_with_tracker(
            artists=artists,
            cutoff_date=cutoff_date,
            incremental=False,
            cassette_name=f"weekly_{fixture_name}_week1"
        )

        results['weeks'].append({
            'week': 1,
            'description': 'Baseline run (90 days)',
            'metrics': week1_metrics
        })

        print(f"  ✓ API Calls: {week1_metrics['api_calls_total']}")
        print(f"  ✓ Lookback: {week1_metrics['lookback_days']} days")
        print(f"  ✓ Execution Time: {week1_metrics['execution_time_seconds']:.2f}s")
        print(f"  ✓ Releases Found: {week1_metrics['releases_found']}")

        # Simulate 1 week passing
        time.sleep(0.5)

        # Week 2: First incremental run
        print("\n📅 WEEK 2: First Incremental Run (7 days since last run)")
        print("-" * 80)

        week2_metrics = self.run_with_tracker(
            artists=artists,
            cutoff_date=cutoff_date,
            incremental=True,
            cassette_name=f"weekly_{fixture_name}_week2"
        )

        results['weeks'].append({
            'week': 2,
            'description': 'Incremental run #1',
            'metrics': week2_metrics
        })

        print(f"  ✓ API Calls: {week2_metrics['api_calls_total']}")
        print(f"  ✓ Lookback: {week2_metrics['lookback_days']} days")
        print(f"  ✓ Execution Time: {week2_metrics['execution_time_seconds']:.2f}s")
        print(f"  ✓ Releases Found: {week2_metrics['releases_found']}")

        # Calculate efficiency gains
        api_reduction = ((week1_metrics['api_calls_total'] - week2_metrics['api_calls_total']) /
                        max(week1_metrics['api_calls_total'], 1)) * 100
        time_reduction = ((week1_metrics['execution_time_seconds'] - week2_metrics['execution_time_seconds']) /
                         max(week1_metrics['execution_time_seconds'], 0.001)) * 100
        lookback_reduction = ((week1_metrics['lookback_days'] - week2_metrics['lookback_days']) /
                             max(week1_metrics['lookback_days'], 1)) * 100

        print(f"\n  📊 Efficiency Gains:")
        print(f"     • API calls reduced: {api_reduction:.1f}%")
        print(f"     • Execution time reduced: {time_reduction:.1f}%")
        print(f"     • Lookback window reduced: {lookback_reduction:.1f}%")

        # Week 3: Second incremental run
        time.sleep(0.5)
        print("\n📅 WEEK 3: Second Incremental Run")
        print("-" * 80)

        week3_metrics = self.run_with_tracker(
            artists=artists,
            cutoff_date=cutoff_date,
            incremental=True,
            cassette_name=f"weekly_{fixture_name}_week3"
        )

        results['weeks'].append({
            'week': 3,
            'description': 'Incremental run #2',
            'metrics': week3_metrics
        })

        print(f"  ✓ API Calls: {week3_metrics['api_calls_total']}")
        print(f"  ✓ Lookback: {week3_metrics['lookback_days']} days")
        print(f"  ✓ Execution Time: {week3_metrics['execution_time_seconds']:.2f}s")

        # Week 4: Third incremental run
        time.sleep(0.5)
        print("\n📅 WEEK 4: Third Incremental Run")
        print("-" * 80)

        week4_metrics = self.run_with_tracker(
            artists=artists,
            cutoff_date=cutoff_date,
            incremental=True,
            cassette_name=f"weekly_{fixture_name}_week4"
        )

        results['weeks'].append({
            'week': 4,
            'description': 'Incremental run #3',
            'metrics': week4_metrics
        })

        print(f"  ✓ API Calls: {week4_metrics['api_calls_total']}")
        print(f"  ✓ Lookback: {week4_metrics['lookback_days']} days")
        print(f"  ✓ Execution Time: {week4_metrics['execution_time_seconds']:.2f}s")

        # Calculate cumulative statistics
        baseline_total_calls = week1_metrics['api_calls_total'] * 4  # 4 weeks of baseline
        incremental_total_calls = (week1_metrics['api_calls_total'] +
                                   week2_metrics['api_calls_total'] +
                                   week3_metrics['api_calls_total'] +
                                   week4_metrics['api_calls_total'])

        total_reduction = ((baseline_total_calls - incremental_total_calls) /
                          max(baseline_total_calls, 1)) * 100

        results['summary'] = {
            'baseline_total_api_calls_4_weeks': baseline_total_calls,
            'incremental_total_api_calls_4_weeks': incremental_total_calls,
            'total_reduction_percent': total_reduction,
            'avg_incremental_lookback_days': (week2_metrics['lookback_days'] +
                                              week3_metrics['lookback_days'] +
                                              week4_metrics['lookback_days']) / 3
        }

        # Print summary
        print("\n" + "=" * 80)
        print("📊 4-WEEK SUMMARY")
        print("=" * 80)
        print(f"\nWithout incremental mode (4 weeks):")
        print(f"  • Total API calls: {baseline_total_calls}")
        print(f"  • Avg lookback: 90 days per run")

        print(f"\nWith incremental mode (4 weeks):")
        print(f"  • Total API calls: {incremental_total_calls}")
        print(f"  • Avg lookback: {results['summary']['avg_incremental_lookback_days']:.1f} days per run")

        print(f"\n💰 EFFICIENCY GAINS:")
        print(f"  • Total API reduction: {total_reduction:.1f}%")
        print(f"  • API calls saved: {baseline_total_calls - incremental_total_calls}")
        print(f"  • Cost savings: ~{total_reduction:.0f}%")

        # Show activity profiles
        print("\n" + "=" * 80)
        print("📊 ARTIST ACTIVITY PROFILES")
        print("=" * 80)

        if week4_metrics.get('activity_profiles'):
            for artist in artists[:5]:  # Show first 5
                profile = week4_metrics['activity_profiles'].get(artist['id'], {})
                print(f"\n{artist['name']}:")
                print(f"  • Frequency: {profile.get('release_frequency', 'unknown')}")
                print(f"  • Last release: {profile.get('last_release_days_ago', 'N/A')} days ago")
                print(f"  • Avg releases/year: {profile.get('avg_releases_per_year', 0)}")
                print(f"  • Recommended check: every {profile.get('recommended_check_interval_days', 30)} days")

        print("=" * 80)

        return results

    def save_results(self, results: Dict[str, Any], output_path: Path) -> None:
        """Save benchmark results to JSON file"""
        output = {
            "benchmark_type": "weekly_run_simulation",
            "benchmark_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "results": results
        }

        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n💾 Results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Weekly Run Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmarks/benchmark_weekly.py --suite weekly_simulation
  python benchmarks/benchmark_weekly.py --suite weekly_simulation --output results/weekly.json
        """
    )

    parser.add_argument(
        '--suite',
        choices=['weekly_simulation', 'all'],
        default='weekly_simulation',
        help='Benchmark suite to run'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output JSON file path (default: results/weekly_TIMESTAMP.json)'
    )

    parser.add_argument(
        '--no-cassettes',
        action='store_true',
        help='Disable cassettes and make real API calls'
    )

    args = parser.parse_args()

    # Determine project root
    project_root = Path(__file__).parent.parent

    # Initialize runner
    use_cassettes = not args.no_cassettes
    runner = WeeklyBenchmarkRunner(project_root, use_cassettes=use_cassettes)

    print("Starting weekly run benchmark...")
    print(f"Cassettes: {'enabled' if use_cassettes else 'disabled'}")
    if use_cassettes and os.environ.get('BENCHMARK_RECORD'):
        print("⚠️  RECORD MODE - Will make real API calls and update cassettes")

    # Run simulation with small fixture
    results = runner.run_weekly_simulation('artists_small')

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = runner.results_dir / f"weekly_{timestamp}.json"

    # Save results
    runner.save_results(results, output_path)

    print("\n✅ Weekly benchmark complete!")


if __name__ == "__main__":
    main()
