#!/usr/bin/env python3
"""
Tests for the profiler module.
"""

import unittest
import time
from artist_tracker.profiler import PerformanceStats, ProfilerContext


class TestPerformanceStats(unittest.TestCase):
    """Tests for PerformanceStats class."""

    def test_api_call_recording(self):
        """Test recording API calls."""
        stats = PerformanceStats()
        stats.record_api_call('search_artist')
        stats.record_api_call('artist_albums')
        stats.record_api_call('search_artist')

        self.assertEqual(stats.total_api_calls, 3)
        self.assertEqual(stats.api_calls['search_artist'], 2)
        self.assertEqual(stats.api_calls['artist_albums'], 1)

    def test_timing_recording(self):
        """Test recording operation timings."""
        stats = PerformanceStats()
        stats.record_timing('fetch_albums', 1.5)
        stats.record_timing('fetch_albums', 2.0)
        stats.record_timing('fetch_tracks', 0.5)

        self.assertEqual(len(stats.timings['fetch_albums']), 2)
        self.assertEqual(len(stats.timings['fetch_tracks']), 1)

    def test_cache_statistics(self):
        """Test cache hit/miss recording."""
        stats = PerformanceStats()
        stats.record_cache_hit()
        stats.record_cache_hit()
        stats.record_cache_miss()

        self.assertEqual(stats.cache_hits, 2)
        self.assertEqual(stats.cache_misses, 1)
        self.assertAlmostEqual(stats.cache_hit_rate, 66.67, places=1)

    def test_total_duration(self):
        """Test total duration calculation."""
        stats = PerformanceStats()
        time.sleep(0.1)
        stats.finish()

        self.assertGreater(stats.total_duration, 0.1)
        self.assertLess(stats.total_duration, 0.2)

    def test_profiler_context(self):
        """Test ProfilerContext timing."""
        stats = PerformanceStats()

        with ProfilerContext(stats, 'test_operation'):
            time.sleep(0.1)

        self.assertEqual(len(stats.timings['test_operation']), 1)
        self.assertGreater(stats.timings['test_operation'][0], 0.1)

    def test_summary_generation(self):
        """Test summary string generation."""
        stats = PerformanceStats()
        stats.record_api_call('search_artist')
        stats.record_api_call('artist_albums')
        stats.record_timing('fetch', 1.0)
        stats.record_cache_hit()
        stats.record_cache_miss()
        stats.finish()

        summary = stats.get_summary()

        self.assertIn('PERFORMANCE PROFILE', summary)
        self.assertIn('API Calls:', summary)
        self.assertIn('Cache Statistics:', summary)
        self.assertIn('Hit Rate:', summary)


if __name__ == '__main__':
    unittest.main()
