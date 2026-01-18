# Performance Optimizations for esh-tracker

Based on benchmark analysis, the following optimizations are recommended:

## 1. **Critical: Fix Cache Effectiveness** ⚠️

**Issue**: Hot cache runs show 0% cache hit rate instead of expected 100%

**Root Cause**:
- Empty cassettes cause API calls to fail before data is fetched
- No releases get cached, so hot cache runs have nothing to retrieve

**Solution**:
```python
# Add cache warming in benchmark setup
def setup_database_with_cache(self, fixture_data):
    # Populate DB with artists
    # Pre-populate cache with mock release data for testing
    # This allows testing cache effectiveness without real API calls
```

**Impact**: Enable proper cache testing, reveal actual cache performance

## 2. **Connection Pooling**

**Issue**: Each API request creates a new connection

**Current**:
```python
# spotipy creates new connections per request
auth_manager = SpotifyClientCredentials(...)
sp = spotipy.Spotify(auth_manager=auth_manager)
```

**Optimization**:
```python
# Reuse connections with session pooling
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=0.3)
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
session.mount('https://', adapter)
```

**Impact**: Reduce connection overhead by ~30-50ms per request

## 3. **Batch ISRC Lookups**

**Issue**: Each track triggers individual ISRC search API call

**Current**: O(n) API calls for n tracks
```python
for track in tracks:
    earliest_date, album = self._get_earliest_release_info(isrc)
```

**Optimization**: Batch lookups to reduce API calls
```python
# Collect all ISRCs first
isrcs = [track['isrc'] for track in tracks if track.get('isrc')]

# Batch lookup (if API supports it) or use async requests
earliest_releases = self._batch_get_earliest_releases(isrcs)
```

**Impact**: Reduce API calls by 60-80% for albums with many tracks

## 4. **Memory Cache Layer**

**Issue**: Database cache requires I/O for every lookup

**Optimization**: Add in-memory LRU cache before database
```python
from functools import lru_cache

class CachedTracker:
    def __init__(self):
        self._memory_cache = {}  # artist_id -> releases

    @lru_cache(maxsize=1000)
    def get_cached_releases(self, artist_id, cutoff_date):
        # Check memory first
        # Then check database
        # Then fetch from API
```

**Impact**: 10-20x faster cache lookups for recently accessed data

## 5. **Parallel Album Processing**

**Issue**: Albums are processed sequentially within each artist

**Current**: Sequential within artist
```python
for album in albums:
    tracks = self.sp.album_tracks(album_id)  # Sequential
```

**Optimization**: Parallel album fetching
```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(self.sp.album_tracks, album['id'])
               for album in albums]
    all_tracks = [f.result() for f in as_completed(futures)]
```

**Impact**: 2-3x faster for artists with many albums

## 6. **Smart Cache TTL**

**Issue**: Fixed 24-hour cache expiry doesn't account for release patterns

**Current**:
```python
max_age_hours = 24  # Fixed
```

**Optimization**: Adaptive TTL based on data freshness
```python
def calculate_cache_ttl(artist_id, last_release_date):
    """
    - Active artists (recent releases): 6 hours
    - Moderate activity: 24 hours
    - Inactive (no recent releases): 7 days
    """
    days_since_release = (datetime.now() - last_release_date).days
    if days_since_release < 30:
        return 6  # Active, check frequently
    elif days_since_release < 180:
        return 24  # Moderate
    else:
        return 168  # Inactive, cache longer
```

**Impact**: Reduce unnecessary API calls by 40-60% for inactive artists

## 7. **Request Debouncing**

**Issue**: Duplicate requests in rapid succession

**Optimization**: Deduplicate concurrent requests
```python
class RequestDeduplicator:
    def __init__(self):
        self._pending = {}  # key -> Future

    async def get_or_wait(self, key, fetch_func):
        if key in self._pending:
            return await self._pending[key]  # Wait for in-flight request

        future = fetch_func()
        self._pending[key] = future
        try:
            return await future
        finally:
            del self._pending[key]
```

**Impact**: Eliminate redundant API calls in concurrent scenarios

## 8. **Database Query Optimization**

**Issue**: Cache queries could be more efficient

**Current**:
```sql
SELECT * FROM releases_cache
WHERE artist_id = ? AND release_date >= ? AND fetched_at >= ?
```

**Optimization**: Add composite indexes
```sql
CREATE INDEX idx_releases_artist_date_fetch
ON releases_cache(artist_id, release_date, fetched_at);
```

**Impact**: 5-10x faster cache lookups with large databases

## 9. **Predictive Prefetching**

**Optimization**: Pre-fetch likely-to-be-accessed artists
```python
def prefetch_popular_artists(self, artist_ids):
    """Warm cache for frequently accessed artists"""
    # Background task to pre-populate cache
    # Run during idle periods
```

**Impact**: Near-zero latency for common queries

## Benchmark Improvements Needed

To properly measure these optimizations:

1. **Populate cassettes with real data**:
   ```bash
   BENCHMARK_RECORD=1 python benchmarks/benchmark.py --suite all
   ```

2. **Add cache-specific metrics**:
   - Cache hit/miss ratio
   - Cache lookup time
   - Memory vs DB cache hits

3. **Add API efficiency metrics**:
   - API calls per release found
   - Redundant call detection
   - Request batching effectiveness

## Priority Order

1. **High Priority** (Immediate impact):
   - Fix cache testing (populate cassettes)
   - Add connection pooling
   - Database query optimization

2. **Medium Priority** (Significant gains):
   - Memory cache layer
   - Batch ISRC lookups
   - Smart cache TTL

3. **Low Priority** (Nice to have):
   - Parallel album processing
   - Request debouncing
   - Predictive prefetching

## Expected Overall Impact

With all optimizations implemented:
- **API calls**: 60-80% reduction through better caching
- **Latency**: 40-60% reduction through connection pooling and memory cache
- **Database load**: 80-90% reduction through memory cache layer
- **Cost**: Proportional reduction in API usage costs
