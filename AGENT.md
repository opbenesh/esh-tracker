# Agent Environment Notes

## Important Guidelines
- **IMPORTANT**: Use a TDD approach to solving problems. *Do not assume* that your solution is correct. Instead, *validate your solution is correct* by first creating a test case and running the test case to _prove_ the solution is working as intended.
- Assume your world knowledge is out of date. Use your web search tool to find up-to-date docs and information.
- When testing APIs, remember to test both mocks and live APIs.
- **IMPORTANT**: Whenever you discover something that you didn't know about this environment, about referenced APIs or used tools, append it to `agent.md`.
- **IMPORTANT**: If you want to perform experiments, put them in an `agent-experiments.py` file. Use separate methods for separate experiments and use `--` style args to run a specific experiment. Do not create additional files for experiments.
- **IMPORTANT**: Please maintain the `README.md` file after any significant changes to ensure documentation stays synchronized with the code.
- **IMPORTANT**: Commit and push changes after completing major features or refactoring steps to ensure work is backed up and synchronized.

## Project Overview for New Agents
### Architecture
- **Core Component**: `SpotifyReleaseTracker` (`src/artist_tracker/tracker.py`) orchestrates API calls and logic.
- **Persistence**: `ArtistDatabase` (`src/artist_tracker/database.py`) manages a SQLite database (`artists.db`) for storing artist IDs.
- **Entry Point**: `main.py` parses CLI args and dispatches commands.

### Key Workflows
1. **Tracking** (`track` command): Fetches recent albums for all artists in DB. Filters by 90-day window. Deduplicates using ISRC and exact name/date matching.
2. **Importing**: Can import from text files or Spotify playlists. Playlist import fetches *all* artists on the playlist.

### Common Pitfalls & Knowledge
- **Spotipy & Markets**: `sp.artist_albums` requires `country` parameter (e.g., 'US'). Other endpoints like `sp.track` use `market`. Mixing them up returns 404s or empty lists.
- **Rate Limiting**: The app handles 429 errors with exponential backoff. Do not remove this logic.
- **Sensitive Data**: Never commit `.env` or `artists.db`.

## Coding Guidelines
- **SOLID Principles**: Follow Single Responsibility, Open-Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion principles for maintainable and extensible code.
- **DRY (Don't Repeat Yourself)**: Avoid code duplication by extracting common logic into reusable functions, classes, or modules.
- **KISS (Keep It Simple, Stupid)**: Strive for simplicity in design and implementation. Avoid over-engineering.
- **Clean Code**: Write readable, self-documenting code with meaningful names, small functions, and clear structure.
- **Error Handling**: Implement robust error handling and logging to aid debugging and maintain reliability.
- **Performance**: Optimize for performance where necessary, but prioritize readability and maintainability.
- **Unix Philosophy**: Adhere to Unix design principles for CLI tools.
    - **Input**: Support standard input (stdin) for data ingestion where applicable (use `-` or detection).
    - **Output**: Separate data (stdout) from informational messages/logs (stderr). Success should often be silent or minimal.
    - **Composition**: Tools should be pipe-friendly.

## Tools & Dependencies
- **Python version**: Python 3.x
- **Package manager**: pip with `requirements.txt`
- **Dependencies**: spotipy, python-dotenv, tqdm
- **Dev dependencies**: mypy (in `requirements-dev.txt`)

## Running the Application
```bash
# Install dependencies first
pip install -r requirements.txt

# Run the tracker
python main.py [command]
```

## Testing
```bash
# Run all tests (unit + live integration)
# Note: PYTHONPATH=src is required because the package is in src/artist_tracker/
PYTHONPATH=src python -m unittest discover tests -v

# Run live integration tests specifically
PYTHONPATH=src python -m unittest tests/test_live.py -v
```

## Configuration
- Credentials stored in `.env` file (git-ignored)
- Required env vars: `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`

## README Design Principles

When maintaining the README, follow these principles:

### 1. Show Value Immediately
- Lead with user benefits and problem-solving, not technical features
- Include a **Quick Example** section high in the doc showing actual output
- Users should understand "why this matters" within the first screen
- Frame features in terms of user pain points (e.g., "never miss a release" vs "90-day tracking window")

### 2. Friendly, Approachable Tone
- Write conversationally, as if helping a friend
- Use emojis in section titles for visual anchors (🎵 🚀 📖 🎯 💡 ❓ etc.)
- Avoid overly formal or academic language
- Be encouraging and assume the user will succeed

### 3. Focus on Main Operations
- Document core workflows thoroughly, mention advanced features briefly
- Don't overwhelm with every option - show the most common use cases
- Users can explore `--help` for exhaustive options
- Quality of examples > quantity of examples

### 4. Relatable Examples
- Use examples from the tool's actual use case (metal/hardcore bands for this project)
- Keep examples consistent throughout the doc (same artist names)
- Show realistic scenarios (e.g., tracking dozens of bands, daily digests)
- Examples should feel authentic to the target user

### 5. Progressive Disclosure
- Quick Example → Installation → Basic Usage → Pro Tips
- Most common use cases appear first, advanced features later
- Keep the initial path to success short and clear

### 6. Scannable Structure
- Use clear, descriptive headings with emojis
- Tables for comparisons (output formats, options)
- Code blocks for all commands
- Bold text for key concepts within paragraphs

### 7. Unix Philosophy (but don't over-explain it)
- Show pipe-friendly defaults in examples
- Demonstrate composition with grep, cron, etc.
- Let the examples speak for themselves rather than lecturing about philosophy

### 8. Practical Troubleshooting
- Address common issues concisely
- Solution-focused (what to do, not just what went wrong)
- Keep it brief - quick answers to common questions

## Performance Optimization Plan

### Context
**Key Insight**: Spotify releases are **read-only** data - once published, they don't change. This makes them perfect candidates for aggressive caching.

### Current Performance Characteristics
1. **API Calls**: Multiple API calls per artist (albums list → album tracks → track details for ISRC)
2. **Concurrency**: Uses ThreadPoolExecutor with 8 workers for artist processing
3. **Caching**: Only in-memory ISRC cache per session (line 316-318 in `tracker.py`)
4. **Database**: SQLite with basic indexing, stores only artist IDs (no release data)
5. **Network**: No request batching, no persistent HTTP connection pooling

### Optimization Phases

#### Phase 1: Persistent Release Caching (High Impact)
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

#### Phase 2: ISRC Lookup Optimization (Medium Impact)
**Problem**: `_get_earliest_release_info()` does separate API search for each ISRC (line 303-354)

**Solution**:
1. Persist ISRC cache to database (new `isrc_lookup` table)
2. Batch ISRC lookups when possible
3. Since ISRC data is immutable, cache can be permanent (no TTL)

**Expected Impact**:
- Eliminate redundant ISRC lookups across sessions
- Reduce API calls by additional 50% for artists with re-released singles

#### Phase 3: Request Optimization (Medium Impact)
**Problem**: Individual API calls for each album's tracks and each track's details

**Solution**:
1. Use Spotify's batch endpoints where available (e.g., `tracks` endpoint accepts up to 50 IDs)
2. Implement HTTP connection pooling (spotipy may already do this, verify)
3. Reduce unnecessary track detail fetches for albums outside date range

**Expected Impact**:
- Reduce total HTTP overhead by 30-40%
- Faster network I/O

#### Phase 4: Database Query Optimization (Low-Medium Impact)
**Problem**: Current database queries are simple but could be optimized for large datasets

**Solution**:
1. Add composite index on `artists(date_added, spotify_artist_id)` for common queries
2. Use `SELECT` with specific columns instead of `SELECT *` where applicable
3. Consider query result caching for frequently accessed data (e.g., `get_artist_count()`)

**Expected Impact**:
- Marginal improvement for small databases (<10k artists)
- Noticeable improvement for large databases (>10k artists)

#### Phase 5: Concurrency Tuning (Low Impact)
**Problem**: Fixed 8-worker ThreadPoolExecutor may not be optimal for all systems

**Solution**:
1. Make max_workers configurable (env var or CLI arg)
2. Implement adaptive concurrency based on API response times
3. Consider async/await pattern with `aiohttp` for better I/O concurrency

**Expected Impact**:
- 10-20% improvement on high-core systems
- Better resource utilization

#### Phase 6: Smart Filtering (Medium Impact)
**Problem**: Fetching all albums then filtering by date is wasteful

**Solution**:
1. Spotify's `artist_albums` doesn't support date filtering, but we can:
   - Stop pagination early when we hit albums before cutoff date (albums are sorted by release_date DESC)
   - Cache the "last checked" date per artist and only look for new releases since then

**Expected Impact**:
- Reduce unnecessary album fetches by 40-60% for artists with large catalogs
- Particularly helpful for prolific artists

### Implementation Priority
1. **Phase 1** (Persistent Release Caching) - Highest ROI
2. **Phase 6** (Smart Filtering) - Quick win, good ROI
3. **Phase 2** (ISRC Optimization) - Good ROI for affected use cases
4. **Phase 3** (Request Optimization) - Moderate effort, moderate gain
5. **Phase 4** (Database Optimization) - Only if scaling issues arise
6. **Phase 5** (Concurrency Tuning) - Lowest priority, niche benefit

### Measurement Strategy
Before optimizing, add instrumentation:
1. Log API call counts per run
2. Track execution time for each phase (fetch albums, fetch tracks, ISRC lookups)
3. Monitor cache hit rates
4. Add `--profile` flag to output performance metrics

### Caching Strategy Details
**Cache Key Design**:
- Releases: `(artist_id, album_id, track_id)` - unique identifier
- ISRC lookups: `(isrc)` - immutable mapping
- TTL Strategy:
  - Releases < 7 days old: 6-hour TTL (might get updated with late additions)
  - Releases 7-90 days old: 24-hour TTL
  - Releases > 90 days old: 7-day TTL (effectively permanent)

**Cache Invalidation**:
- Manual: `track --force-refresh` bypasses all caches
- Automatic: TTL-based expiration
- Selective: `--refresh-artist <id>` to refresh specific artist

### Testing Considerations
- Test with both empty cache (first run) and warm cache (subsequent runs)
- Verify cache invalidation works correctly
- Test with artists who have >50 albums (pagination)
- Validate that cached data matches fresh API data
- Performance benchmarks: track time for 10, 50, 100 artists

## Performance Insights

This section documents interesting performance characteristics and insights discovered during development and optimization work.

### Baseline Metrics
*Document baseline performance here as you gather data*

**Example format**:
```
Date: YYYY-MM-DD
Test: Tracking 50 artists, 90-day lookback, cold cache
- Total time: X.XX seconds
- API calls: XXX
- Cache hits: X%
- Bottlenecks: [description]
```

### Discoveries
*Add interesting findings here as you work on optimizations*

**Example entries**:
- "ISRC lookups account for 60% of API calls but only 10% are unique across sessions"
- "Albums endpoint pagination causes N+1 problem for artists with >50 releases"
- "ThreadPoolExecutor with 8 workers is bottlenecked by API rate limits, not CPU"
