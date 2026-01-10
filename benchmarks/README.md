# Benchmark Suite

This benchmark suite provides **reproducible performance measurements** for the Spotify Release Tracker across different machines and time periods.

## Design Principles

### Reproducibility Guarantees

The benchmark suite is designed to return **consistent API call counts** regardless of:
- Which machine it runs on
- When it's run (today vs. 6 months from now)
- Network speed or latency
- Spotify adding new releases

### How Consistency is Achieved

1. **Fixed Artist IDs** - Uses Spotify artist IDs (not names) to avoid search API variation
2. **Fixed Cutoff Dates** - Uses dates in the past (e.g., `2024-12-31`) to ensure immutable data
3. **Immutable Past Releases** - Assumes Spotify releases before the cutoff date never change
4. **API Calls as Primary Metric** - Counts API calls (network-independent) rather than execution time

### What Can Vary

While API call counts should be identical, these metrics may vary:
- **Execution time** - Depends on network speed, machine performance, Spotify API latency
- **Wall clock time** - Includes Python startup, database I/O overhead
- **Absolute cache hit rates** - May vary slightly on first run due to system state

## Benchmark Suites

### Small Suite (`artists_small`)
- **10 artists** with varied release patterns
- Quick smoke test (~30-60 seconds per scenario)
- Good for development and CI/CD

### Medium Suite (`artists_medium`)
- **30 artists** across multiple genres
- Realistic workload (~2-5 minutes per scenario)
- Good for performance validation

### Large Suite (`artists_large`)
- **50 artists** including prolific artists with 100+ albums
- Stress test for pagination and caching (~5-15 minutes per scenario)
- Good for scalability testing

## Running Benchmarks

### Prerequisites

Ensure you have Spotify API credentials configured:
```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
# Or create a .env file with these values
```

### Basic Usage

Run the small benchmark suite:
```bash
python benchmarks/benchmark.py --suite small
```

Run all suites:
```bash
python benchmarks/benchmark.py --suite all
```

Save results to a specific file:
```bash
python benchmarks/benchmark.py --suite medium --output results/my_benchmark.json
```

### What Gets Tested

Each suite runs **two scenarios** per fixture:

1. **Cold Cache** - Fresh database, no cached data
   - Measures API calls needed to fetch all data from scratch
   - Tests cache population logic

2. **Hot Cache** - Immediately after cold cache run
   - Measures API calls with fully populated cache
   - Tests cache retrieval efficiency
   - Should show significant reduction in API calls

## Understanding Results

### Terminal Output

During execution, you'll see:
```
================================================================================
Running: artists_small_cold
Cache mode: COLD
Artists: 10
Cutoff date: 2024-12-31
================================================================================
Setting up fresh database...
Executing track command...

Results:
  API Calls: 145
  Cache Hit Rate: 0.0%
  Execution Time: 12.34s
  Releases Found: 87
```

### Summary Comparison

At the end, a summary compares cold vs. hot cache:
```
ARTISTS_SMALL
--------------------------------------------------------------------------------
Metric                         Cold Cache      Hot Cache       Improvement
--------------------------------------------------------------------------------
API Calls                      145             8               94.5%
Cache Hit Rate                 0.0%            98.2%
Execution Time (s)             12.34s          0.52s           95.8%
Releases Found                 87              87
```

### JSON Output

Results are saved in structured JSON format:
```json
{
  "benchmark_version": "1.0",
  "timestamp": "2026-01-10T12:34:56Z",
  "environment": {
    "python_version": "3.11.0",
    "platform": "linux"
  },
  "results": [
    {
      "scenario": "artists_small_cold",
      "cache_mode": "cold",
      "artist_count": 10,
      "cutoff_date": "2024-12-31",
      "metrics": {
        "api_calls_total": 145,
        "api_calls": {
          "artist_albums": 10,
          "album_tracks": 45,
          "track": 80,
          "search_isrc": 10
        },
        "cache_hits": 0,
        "cache_misses": 145,
        "cache_hit_rate": 0.0,
        "execution_time_seconds": 12.34,
        "releases_found": 87
      }
    }
  ]
}
```

## Key Metrics Explained

### API Calls Total
**Expected consistency:** ✅ Should be identical across runs
- Total number of Spotify API requests made
- Primary metric for reproducibility
- Cold cache: High count (fetching all data)
- Hot cache: Low count (only checking for updates)

### API Call Breakdown
**Expected consistency:** ✅ Should be identical across runs
- `artist_albums`: Fetching album lists (1 per artist + pagination)
- `album_tracks`: Fetching tracks from albums
- `track`: Getting detailed track info (ISRC, popularity)
- `search_isrc`: ISRC deduplication lookups

### Cache Hit Rate
**Expected consistency:** ⚠️ May vary slightly
- Percentage of data retrieved from cache vs. API
- Cold cache: ~0% (nothing cached yet)
- Hot cache: 80-95% (most data cached)

### Execution Time
**Expected consistency:** ❌ Varies by machine/network
- Wall clock time for the track command
- Useful for relative comparison (cold vs. hot)
- Not suitable for cross-machine comparison

### Releases Found
**Expected consistency:** ✅ Should be identical across runs
- Number of releases matching the criteria
- Should be the same for cold and hot cache runs
- Validates cache doesn't affect results

## Comparing Results Across Machines

### What to Compare

✅ **Safe to compare:**
- API call counts (should match exactly)
- API call breakdown (should match exactly)
- Releases found (should match exactly)
- Cache hit rate improvement (cold → hot)

❌ **Not comparable:**
- Absolute execution times (network/hardware dependent)
- Wall clock times

### Example Comparison

Machine A (2024-01-10):
```json
{
  "scenario": "artists_small_cold",
  "metrics": {
    "api_calls_total": 145,
    "api_calls": {"artist_albums": 10, "album_tracks": 45, "track": 80, "search_isrc": 10}
  }
}
```

Machine B (2024-06-15):
```json
{
  "scenario": "artists_small_cold",
  "metrics": {
    "api_calls_total": 145,
    "api_calls": {"artist_albums": 10, "album_tracks": 45, "track": 80, "search_isrc": 10}
  }
}
```

✅ **These results match!** The code has consistent performance.

## Interpreting Performance Changes

### Expected Behavior

| Change | Cold Cache API Calls | Hot Cache API Calls | Interpretation |
|--------|---------------------|---------------------|----------------|
| No change | Same | Same | ✅ Performance stable |
| Optimization | Same or lower | Same or lower | ✅ Improvement |
| Regression | Higher | Higher | ⚠️ Performance degradation |
| Cache issue | Same | Higher than expected | ⚠️ Cache not working |

### Typical Results

For the **small suite** (10 artists, 2024 releases):
- Cold cache: ~100-200 API calls
- Hot cache: ~10-30 API calls (checking for updates)
- Improvement: 80-95% reduction

For the **large suite** (50 artists):
- Cold cache: ~500-1500 API calls
- Hot cache: ~50-150 API calls
- Improvement: 85-95% reduction

## Scenarios Tested

### Cold vs. Hot Cache
- **Primary test**: Validates caching effectiveness
- **Expected**: 80-95% API call reduction in hot cache

### Small vs. Medium vs. Large
- **Scalability test**: Validates performance scales linearly
- **Expected**: API calls should scale proportionally with artist count

### ISRC Deduplication
- **Implicit test**: Tracks with same ISRC on multiple albums
- **Expected**: `search_isrc` calls << total tracks (indicates dedup working)

## Advanced Usage

### Running a Single Scenario Manually

For debugging, you can manually run the track command:

```bash
# Cold cache - remove database first
rm artists.db

# Import artists from fixture
python main.py import-txt <(jq -r '.artists[].id | "spotify:artist:\(.)"' benchmarks/fixtures/artists_small.json)

# Run with profiling
python main.py track --since 2024-12-31 --profile

# Hot cache - run again immediately
python main.py track --since 2024-12-31 --profile
```

### Creating Custom Fixtures

Create a new JSON file in `benchmarks/fixtures/`:

```json
{
  "description": "My custom benchmark",
  "cutoff_date": "2024-12-31",
  "artists": [
    {"id": "SPOTIFY_ARTIST_ID", "name": "Artist Name", "note": "Optional note"}
  ]
}
```

Then run:
```bash
python benchmarks/benchmark.py --suite my_custom
```

### Continuous Integration

For CI/CD pipelines, you can:
1. Run benchmarks on each commit
2. Compare results to baseline
3. Alert if API calls increase significantly

```bash
# Run benchmark and save results
python benchmarks/benchmark.py --suite small --output results/ci_run.json

# Compare to baseline (custom script needed)
python scripts/compare_benchmarks.py results/baseline.json results/ci_run.json
```

## Troubleshooting

### "No releases found" in results
- Check Spotify API credentials are valid
- Verify artists in fixture have releases before cutoff date
- Check network connectivity

### API calls higher than expected
- Ensure database was cleaned for cold cache run
- Check for rate limiting (may trigger retries)
- Verify cutoff date is in the past (not future)

### Results vary between runs
- **API calls**: Should be identical - investigate if different
- **Time**: Expected to vary - ignore for consistency checks
- **Cache hit rate**: May vary slightly on very first run

### Permission errors
- Ensure benchmark script is executable: `chmod +x benchmarks/benchmark.py`
- Ensure results directory is writable

## Future Enhancements

Potential additions to the benchmark suite:
- [ ] Comparison tool for analyzing result JSON files
- [ ] Historical trend tracking
- [ ] Memory usage profiling
- [ ] Database query performance metrics
- [ ] Network retry statistics
- [ ] CI/CD integration example

## Contributing

When adding new benchmarks:
1. Use fixed artist IDs (not names)
2. Use fixed cutoff dates in the past
3. Document expected API call ranges
4. Test consistency across multiple runs
