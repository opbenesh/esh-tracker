# TODO - Artist Tracker

## Performance Optimization Tasks

### Context
**Key Insight**: Spotify releases are **read-only** data - once published, they don't change. This makes them perfect candidates for aggressive caching.

### Current Performance Characteristics
1. **API Calls**: Multiple API calls per artist (albums list → album tracks → track details for ISRC)
2. **Concurrency**: Uses ThreadPoolExecutor with 8 workers for artist processing
3. **Caching**: Only in-memory ISRC cache per session (line 316-318 in `tracker.py`)
4. **Database**: SQLite with basic indexing, stores only artist IDs (no release data)
5. **Network**: No request batching, no persistent HTTP connection pooling

---

## Optimization Phases

### Phase 1: Persistent Release Caching (High Impact) ⭐
**Status**: Not started
**Priority**: HIGHEST ROI

**Problem**: Every `track` command re-fetches all album/track data from Spotify API, even though releases are immutable.

**Solution**: Add persistent cache table for release data
- Create `releases` table in SQLite to cache album/track data
- Schema: `(artist_id, album_id, track_id, isrc, release_date, album_name, track_name, album_type, popularity, spotify_url, fetched_at)`
- Key: Only fetch from API if data is older than configurable TTL (default: 24 hours for recent releases, 7 days for older)
- Index on `(artist_id, release_date)` for fast filtering

**Expected Impact**:
- Reduce API calls by 80-90% for repeat runs
- Speed up track command by 5-10x for subsequent runs
- Respect API rate limits better

**Implementation Notes**:
- Add `--force-refresh` flag to bypass cache
- Cache invalidation: releases older than 30 days can have longer TTL (they won't change)
- Consider separating "cache" from "persistent storage" concepts

**Tasks**:
- [ ] Design database schema for releases cache
- [ ] Implement cache layer in database.py
- [ ] Add TTL-based cache lookup in tracker.py
- [ ] Add `--force-refresh` CLI flag
- [ ] Write tests for cache hit/miss scenarios
- [ ] Add cache statistics to output (optional --verbose)

---

### Phase 6: Smart Filtering (Medium Impact) ⭐
**Status**: Not started
**Priority**: Quick win, good ROI

**Problem**: Fetching all albums then filtering by date is wasteful

**Solution**:
1. Spotify's `artist_albums` doesn't support date filtering, but we can:
   - Stop pagination early when we hit albums before cutoff date (albums are sorted by release_date DESC)
   - Cache the "last checked" date per artist and only look for new releases since then

**Expected Impact**:
- Reduce unnecessary album fetches by 40-60% for artists with large catalogs
- Particularly helpful for prolific artists

**Tasks**:
- [ ] Implement early pagination stopping in `_get_recent_releases()`
- [ ] Add `last_checked` column to artists table
- [ ] Update logic to only fetch new releases since last check
- [ ] Test with prolific artists (>50 albums)

---

### Phase 2: ISRC Lookup Optimization (Medium Impact)
**Status**: Not started
**Priority**: Good ROI for affected use cases

**Problem**: `_get_earliest_release_info()` does separate API search for each ISRC (line 303-354)

**Solution**:
1. Persist ISRC cache to database (new `isrc_lookup` table)
2. Batch ISRC lookups when possible
3. Since ISRC data is immutable, cache can be permanent (no TTL)

**Expected Impact**:
- Eliminate redundant ISRC lookups across sessions
- Reduce API calls by additional 50% for artists with re-released singles

**Tasks**:
- [ ] Create `isrc_lookup` table in database
- [ ] Implement persistent ISRC cache in database.py
- [ ] Update `_get_earliest_release_info()` to use persistent cache
- [ ] Investigate batch ISRC lookup possibilities
- [ ] Write tests for ISRC cache

---

### Phase 3: Request Optimization (Medium Impact)
**Status**: Not started
**Priority**: Moderate effort, moderate gain

**Problem**: Individual API calls for each album's tracks and each track's details

**Solution**:
1. Use Spotify's batch endpoints where available (e.g., `tracks` endpoint accepts up to 50 IDs)
2. Implement HTTP connection pooling (spotipy may already do this, verify)
3. Reduce unnecessary track detail fetches for albums outside date range

**Expected Impact**:
- Reduce total HTTP overhead by 30-40%
- Faster network I/O

**Tasks**:
- [ ] Research Spotify batch endpoints
- [ ] Refactor to batch track detail fetches
- [ ] Verify spotipy connection pooling behavior
- [ ] Profile before/after to measure gains

---

### Phase 4: Database Query Optimization (Low-Medium Impact)
**Status**: Not started
**Priority**: Only if scaling issues arise

**Problem**: Current database queries are simple but could be optimized for large datasets

**Solution**:
1. Add composite index on `artists(date_added, spotify_artist_id)` for common queries
2. Use `SELECT` with specific columns instead of `SELECT *` where applicable
3. Consider query result caching for frequently accessed data (e.g., `get_artist_count()`)

**Expected Impact**:
- Marginal improvement for small databases (<10k artists)
- Noticeable improvement for large databases (>10k artists)

**Tasks**:
- [ ] Profile database queries with large dataset
- [ ] Add composite indexes where beneficial
- [ ] Optimize SELECT queries
- [ ] Implement query result caching

---

### Phase 5: Concurrency Tuning (Low Impact)
**Status**: Not started
**Priority**: Lowest priority, niche benefit

**Problem**: Fixed 8-worker ThreadPoolExecutor may not be optimal for all systems

**Solution**:
1. Make max_workers configurable (env var or CLI arg)
2. Implement adaptive concurrency based on API response times
3. Consider async/await pattern with `aiohttp` for better I/O concurrency

**Expected Impact**:
- 10-20% improvement on high-core systems
- Better resource utilization

**Tasks**:
- [ ] Add `--workers` CLI flag or `MAX_WORKERS` env var
- [ ] Implement adaptive concurrency logic
- [ ] Research async/await migration (breaking change, needs evaluation)

---

## Pre-Implementation: Instrumentation

**Status**: Not started
**Priority**: Should be done BEFORE optimization work

Before optimizing, add instrumentation to measure baseline performance:

**Tasks**:
- [ ] Add API call counter to tracker
- [ ] Add timing measurements for each phase (fetch albums, fetch tracks, ISRC lookups)
- [ ] Add `--profile` flag to output performance metrics
- [ ] Create performance logging infrastructure
- [ ] Document baseline metrics in AGENT.md Performance Insights section

---

## Implementation Priority

1. **Instrumentation** - Do this FIRST to establish baselines
2. **Phase 1** (Persistent Release Caching) - Highest ROI
3. **Phase 6** (Smart Filtering) - Quick win, good ROI
4. **Phase 2** (ISRC Optimization) - Good ROI for affected use cases
5. **Phase 3** (Request Optimization) - Moderate effort, moderate gain
6. **Phase 4** (Database Optimization) - Only if scaling issues arise
7. **Phase 5** (Concurrency Tuning) - Lowest priority, niche benefit

---

## Caching Strategy Details

### Cache Key Design
- **Releases**: `(artist_id, album_id, track_id)` - unique identifier
- **ISRC lookups**: `(isrc)` - immutable mapping

### TTL Strategy
- Releases < 7 days old: 6-hour TTL (might get updated with late additions)
- Releases 7-90 days old: 24-hour TTL
- Releases > 90 days old: 7-day TTL (effectively permanent)

### Cache Invalidation
- Manual: `track --force-refresh` bypasses all caches
- Automatic: TTL-based expiration
- Selective: `--refresh-artist <id>` to refresh specific artist

---

## Testing Considerations

When implementing optimizations, ensure:
- [ ] Test with both empty cache (first run) and warm cache (subsequent runs)
- [ ] Verify cache invalidation works correctly
- [ ] Test with artists who have >50 albums (pagination)
- [ ] Validate that cached data matches fresh API data
- [ ] Performance benchmarks: track time for 10, 50, 100 artists
- [ ] Test edge cases (rate limits, network errors, partial cache)

---

## Other TODOs

*Add other non-performance tasks here as they come up*
