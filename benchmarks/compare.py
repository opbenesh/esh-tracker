#!/usr/bin/env python3
"""
Benchmark Comparison Tool

Compares two benchmark result JSON files to identify performance changes.
Useful for validating that code changes don't introduce regressions.

Usage:
    python benchmarks/compare.py baseline.json current.json
    python benchmarks/compare.py results/before.json results/after.json --threshold 5
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


class BenchmarkComparator:
    """Compares two benchmark results and identifies changes"""

    def __init__(self, threshold_percent: float = 5.0):
        """
        Args:
            threshold_percent: Percentage change threshold for warnings (default: 5%)
        """
        self.threshold = threshold_percent

    def load_results(self, filepath: Path) -> Dict[str, Any]:
        """Load benchmark results from JSON file"""
        with open(filepath, 'r') as f:
            return json.load(f)

    def find_matching_scenario(self, scenario: Dict[str, Any],
                                results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find matching scenario in comparison results"""
        target_name = scenario['scenario']
        target_cache = scenario['cache_mode']

        for result in results:
            if result['scenario'] == target_name and result['cache_mode'] == target_cache:
                return result

        return None

    def compare_metrics(self, baseline: Dict[str, Any],
                       current: Dict[str, Any]) -> Dict[str, Any]:
        """Compare metrics between two scenarios"""
        comparison = {
            'scenario': baseline['scenario'],
            'cache_mode': baseline['cache_mode'],
            'changes': {},
            'warnings': [],
            'improvements': [],
            'regressions': []
        }

        base_metrics = baseline['metrics']
        curr_metrics = current['metrics']

        # Compare API calls total
        base_api = base_metrics['api_calls_total']
        curr_api = curr_metrics['api_calls_total']

        if base_api != curr_api:
            change_pct = ((curr_api - base_api) / base_api * 100) if base_api > 0 else 0
            comparison['changes']['api_calls_total'] = {
                'baseline': base_api,
                'current': curr_api,
                'change': curr_api - base_api,
                'change_percent': change_pct
            }

            if curr_api > base_api:
                comparison['regressions'].append(
                    f"API calls increased: {base_api} → {curr_api} (+{change_pct:.1f}%)"
                )
                if abs(change_pct) >= self.threshold:
                    comparison['warnings'].append(
                        f"⚠️  API calls increased by {change_pct:.1f}% (threshold: {self.threshold}%)"
                    )
            else:
                comparison['improvements'].append(
                    f"API calls decreased: {base_api} → {curr_api} ({change_pct:.1f}%)"
                )

        # Compare API call breakdown
        base_breakdown = base_metrics['api_calls']
        curr_breakdown = curr_metrics['api_calls']

        all_endpoints = set(base_breakdown.keys()) | set(curr_breakdown.keys())
        breakdown_changes = {}

        for endpoint in all_endpoints:
            base_count = base_breakdown.get(endpoint, 0)
            curr_count = curr_breakdown.get(endpoint, 0)

            if base_count != curr_count:
                change_pct = ((curr_count - base_count) / base_count * 100) if base_count > 0 else 0
                breakdown_changes[endpoint] = {
                    'baseline': base_count,
                    'current': curr_count,
                    'change': curr_count - base_count,
                    'change_percent': change_pct
                }

        if breakdown_changes:
            comparison['changes']['api_call_breakdown'] = breakdown_changes

        # Compare cache hit rate
        base_hit_rate = base_metrics['cache_hit_rate']
        curr_hit_rate = curr_metrics['cache_hit_rate']

        if abs(base_hit_rate - curr_hit_rate) > 1.0:  # More than 1 percentage point
            comparison['changes']['cache_hit_rate'] = {
                'baseline': base_hit_rate,
                'current': curr_hit_rate,
                'change': curr_hit_rate - base_hit_rate
            }

            if curr_hit_rate < base_hit_rate:
                comparison['regressions'].append(
                    f"Cache hit rate decreased: {base_hit_rate:.1f}% → {curr_hit_rate:.1f}%"
                )
            else:
                comparison['improvements'].append(
                    f"Cache hit rate improved: {base_hit_rate:.1f}% → {curr_hit_rate:.1f}%"
                )

        # Compare releases found (should always match)
        base_releases = base_metrics['releases_found']
        curr_releases = curr_metrics['releases_found']

        if base_releases != curr_releases:
            comparison['changes']['releases_found'] = {
                'baseline': base_releases,
                'current': curr_releases,
                'change': curr_releases - base_releases
            }
            comparison['warnings'].append(
                f"⚠️  Releases found changed: {base_releases} → {curr_releases} "
                f"(should be identical for same cutoff date)"
            )

        # Compare execution time (informational only)
        base_time = base_metrics['execution_time_seconds']
        curr_time = curr_metrics['execution_time_seconds']

        if base_time > 0:
            time_change_pct = ((curr_time - base_time) / base_time * 100)
            comparison['changes']['execution_time'] = {
                'baseline': base_time,
                'current': curr_time,
                'change': curr_time - base_time,
                'change_percent': time_change_pct
            }

        return comparison

    def compare_results(self, baseline_path: Path, current_path: Path) -> Dict[str, Any]:
        """Compare two benchmark result files"""
        baseline_data = self.load_results(baseline_path)
        current_data = self.load_results(current_path)

        baseline_results = baseline_data['results']
        current_results = current_data['results']

        comparisons = []
        missing_scenarios = []

        for baseline_scenario in baseline_results:
            current_scenario = self.find_matching_scenario(baseline_scenario, current_results)

            if current_scenario is None:
                missing_scenarios.append(baseline_scenario['scenario'])
                continue

            comparison = self.compare_metrics(baseline_scenario, current_scenario)
            comparisons.append(comparison)

        return {
            'baseline_file': str(baseline_path),
            'current_file': str(current_path),
            'baseline_timestamp': baseline_data.get('timestamp', 'unknown'),
            'current_timestamp': current_data.get('timestamp', 'unknown'),
            'comparisons': comparisons,
            'missing_scenarios': missing_scenarios
        }

    def print_report(self, comparison_result: Dict[str, Any]) -> bool:
        """
        Print a human-readable comparison report

        Returns:
            bool: True if no regressions found, False otherwise
        """
        print(f"\n{'='*80}")
        print("BENCHMARK COMPARISON REPORT")
        print(f"{'='*80}\n")

        print(f"Baseline: {comparison_result['baseline_file']}")
        print(f"          {comparison_result['baseline_timestamp']}")
        print(f"Current:  {comparison_result['current_file']}")
        print(f"          {comparison_result['current_timestamp']}")
        print()

        has_regressions = False
        total_improvements = 0
        total_regressions = 0
        total_warnings = 0

        for comp in comparison_result['comparisons']:
            scenario = comp['scenario']
            cache_mode = comp['cache_mode']

            print(f"\n{scenario} ({cache_mode} cache)")
            print("-" * 80)

            # Print warnings first
            if comp['warnings']:
                for warning in comp['warnings']:
                    print(f"  {warning}")
                total_warnings += len(comp['warnings'])
                print()

            # Print improvements
            if comp['improvements']:
                print("  ✅ Improvements:")
                for improvement in comp['improvements']:
                    print(f"     {improvement}")
                total_improvements += len(comp['improvements'])
                print()

            # Print regressions
            if comp['regressions']:
                print("  ❌ Regressions:")
                for regression in comp['regressions']:
                    print(f"     {regression}")
                total_regressions += len(comp['regressions'])
                has_regressions = True
                print()

            # Print detailed changes
            if comp['changes']:
                if not (comp['improvements'] or comp['regressions']):
                    print("  📊 Changes:")

                # API call breakdown
                if 'api_call_breakdown' in comp['changes']:
                    print("     API Call Breakdown:")
                    for endpoint, change in comp['changes']['api_call_breakdown'].items():
                        direction = "+" if change['change'] > 0 else ""
                        print(f"       {endpoint}: {change['baseline']} → {change['current']} "
                              f"({direction}{change['change_percent']:.1f}%)")

                # Execution time (informational)
                if 'execution_time' in comp['changes']:
                    time_change = comp['changes']['execution_time']
                    direction = "+" if time_change['change'] > 0 else ""
                    print(f"     Execution time: {time_change['baseline']:.2f}s → "
                          f"{time_change['current']:.2f}s ({direction}{time_change['change_percent']:.1f}%)")
                    print("     (Note: Execution time varies by network/hardware)")

                print()

            # No changes
            if not comp['changes']:
                print("  ✅ No changes detected - performance is identical")
                print()

        # Missing scenarios
        if comparison_result['missing_scenarios']:
            print(f"\n⚠️  Missing Scenarios in Current Results:")
            for scenario in comparison_result['missing_scenarios']:
                print(f"   - {scenario}")
            print()

        # Summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}\n")
        print(f"  Improvements: {total_improvements}")
        print(f"  Regressions:  {total_regressions}")
        print(f"  Warnings:     {total_warnings}")

        if has_regressions or total_warnings > 0:
            print(f"\n  ❌ REGRESSIONS DETECTED - Review changes above")
            print(f"{'='*80}\n")
            return False
        else:
            print(f"\n  ✅ NO REGRESSIONS - Performance is stable or improved")
            print(f"{'='*80}\n")
            return True


def main():
    parser = argparse.ArgumentParser(
        description="Compare two benchmark results to identify performance changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare before and after optimization
  python benchmarks/compare.py results/before.json results/after.json

  # Use stricter threshold (2% instead of default 5%)
  python benchmarks/compare.py baseline.json current.json --threshold 2

  # Exit with error code if regressions found (useful for CI/CD)
  python benchmarks/compare.py baseline.json current.json --strict
        """
    )

    parser.add_argument(
        'baseline',
        type=str,
        help='Baseline benchmark results (JSON file)'
    )

    parser.add_argument(
        'current',
        type=str,
        help='Current benchmark results (JSON file)'
    )

    parser.add_argument(
        '--threshold',
        type=float,
        default=5.0,
        help='Percentage change threshold for warnings (default: 5.0)'
    )

    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit with error code (1) if any regressions are found'
    )

    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    # Validate files exist
    if not baseline_path.exists():
        print(f"Error: Baseline file not found: {baseline_path}", file=sys.stderr)
        sys.exit(1)

    if not current_path.exists():
        print(f"Error: Current file not found: {current_path}", file=sys.stderr)
        sys.exit(1)

    # Run comparison
    comparator = BenchmarkComparator(threshold_percent=args.threshold)
    comparison_result = comparator.compare_results(baseline_path, current_path)

    # Print report
    no_regressions = comparator.print_report(comparison_result)

    # Exit with appropriate code
    if args.strict and not no_regressions:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
