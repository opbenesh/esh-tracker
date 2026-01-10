#!/usr/bin/env python3
"""
Performance Profiler for Artist Tracker

Tracks API calls, timings, and other performance metrics.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceStats:
    """Container for performance statistics."""

    # API call counts by endpoint type
    api_calls: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Timing data by operation type
    timings: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))

    # Cache statistics
    cache_hits: int = 0
    cache_misses: int = 0

    # Overall timing
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    def record_api_call(self, endpoint: str):
        """Record an API call to a specific endpoint."""
        self.api_calls[endpoint] += 1

    def record_timing(self, operation: str, duration: float):
        """Record timing for an operation."""
        self.timings[operation].append(duration)

    def record_cache_hit(self):
        """Record a cache hit."""
        self.cache_hits += 1

    def record_cache_miss(self):
        """Record a cache miss."""
        self.cache_misses += 1

    def finish(self):
        """Mark the end of profiling."""
        self.end_time = time.time()

    @property
    def total_api_calls(self) -> int:
        """Total number of API calls made."""
        return sum(self.api_calls.values())

    @property
    def total_duration(self) -> float:
        """Total duration of the profiled operation."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def cache_hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100

    def get_summary(self) -> str:
        """Get a formatted summary of performance statistics."""
        lines = []
        lines.append("=" * 80)
        lines.append("PERFORMANCE PROFILE")
        lines.append("=" * 80)
        lines.append(f"Total Duration: {self.total_duration:.2f}s")
        lines.append("")

        # API calls breakdown
        lines.append(f"API Calls: {self.total_api_calls} total")
        if self.api_calls:
            for endpoint, count in sorted(self.api_calls.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - {endpoint}: {count}")
        lines.append("")

        # Cache statistics
        if self.cache_hits > 0 or self.cache_misses > 0:
            lines.append("Cache Statistics:")
            lines.append(f"  - Hits: {self.cache_hits}")
            lines.append(f"  - Misses: {self.cache_misses}")
            lines.append(f"  - Hit Rate: {self.cache_hit_rate:.1f}%")
            lines.append("")

        # Timing breakdown
        if self.timings:
            lines.append("Operation Timings:")
            for operation, durations in sorted(self.timings.items()):
                if durations:
                    avg = sum(durations) / len(durations)
                    total = sum(durations)
                    lines.append(f"  - {operation}:")
                    lines.append(f"      Count: {len(durations)}")
                    lines.append(f"      Total: {total:.2f}s")
                    lines.append(f"      Avg: {avg:.3f}s")
                    lines.append(f"      Min: {min(durations):.3f}s")
                    lines.append(f"      Max: {max(durations):.3f}s")

        lines.append("=" * 80)
        return "\n".join(lines)


class ProfilerContext:
    """Context manager for timing operations."""

    def __init__(self, stats: PerformanceStats, operation: str):
        """
        Initialize profiler context.

        Args:
            stats: PerformanceStats instance to record to
            operation: Name of the operation being timed
        """
        self.stats = stats
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record duration."""
        duration = time.time() - self.start_time
        self.stats.record_timing(self.operation, duration)
        return False
