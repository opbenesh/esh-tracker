# AGENTS.md

## Important Guidelines
- **IMPORTANT**: Use a TDD approach to solving problems. *Do not assume* that your solution is correct. Instead, *validate your solution is correct* by first creating a test case and running the test case to _prove_ the solution is working as intended.
- **CRITICAL - Bug Fix Workflow**: Whenever you discover a bug, follow this mandatory process:
  1. **Add a test case** that reproduces the bug
  2. **Run the test** and verify it fails (proving the bug exists)
  3. **Fix the bug** in the source code
  4. **Run the test again** and verify it passes (proving the fix works)
  5. **Run all tests** to ensure no regressions were introduced
  This ensures bugs stay fixed and prevents regression.
- Assume your world knowledge is out of date. Use your web search tool to find up-to-date docs and information.
- When testing APIs, remember to test both mocks and live APIs.
- **IMPORTANT**: Whenever you discover something that you didn't know about this environment, about referenced APIs or used tools, append it to `AGENTS.md`.
- **IMPORTANT**: If you want to perform experiments, put them in an `agent-experiments.py` file. Use separate methods for separate experiments and use `--` style args to run a specific experiment. Do not create additional files for experiments.
- **IMPORTANT**: Please maintain the `README.md` file after any significant changes to ensure documentation stays synchronized with the code.
- **IMPORTANT**: Commit and push changes after completing major features or refactoring steps to ensure work is backed up and synchronized.

## Project Overview
### Architecture
- **Core Component**: `SpotifyReleaseTracker` (`src/artist_tracker/tracker.py`) orchestrates API calls and logic.
- **Persistence**: `ArtistDatabase` (`src/artist_tracker/database.py`) manages a SQLite database (`artists.db`) for storing artist IDs.
- **Entry Point**: `main.py` parses CLI args and dispatches commands.

### Key Workflows
1. **Playlist-First Tracking** (`track` command): User points to a playlist (or multiple), app fetches artists, then checks for recent releases. This is the main workflow.
2. **Liked Songs Tracking** (`track --liked`): Tracks releases from artists in the user's "Liked Songs" library.
3. **Caching**: SQLite database (`artists.db`) is used behind the scenes to cache release data and ISRC lookups to minimize API calls, but explicit artist management (importing to DB) has been removed to simplify UX.

### Common Pitfalls & Knowledge
- **Spotipy & Markets**: `sp.artist_albums` requires `country` parameter (e.g., 'US'). Other endpoints like `sp.track` use `market`. Mixing them up returns 404s or empty lists.
- **Rate Limiting**: The app handles 429 errors with exponential backoff. Do not remove this logic.
- **Sensitive Data**: Never commit `.env` or `artists.db`.

## Setup commands
### Tools & Dependencies
- **Python version**: Python 3.x
- **Package manager**: pip with `requirements.txt`
- **Dependencies**: spotipy, python-dotenv, tqdm
- **Dev dependencies**: mypy (in `requirements-dev.txt`)

### Running the Application
```bash
# Install dependencies first
pip install -r requirements.txt

# Run the tracker (Playlist-First Flow)
python main.py track <playlist-id>

# Track from multiple playlists
python main.py track <playlist-1> <playlist-2>

# Track from "Liked Songs"
python main.py track --liked

# Demo single artist
python main.py track --artist="Megadeth"
```

## Code style
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

## Testing instructions
```bash
# Run all tests (unit + live integration)
# Note: PYTHONPATH=src is required because the package is in src/artist_tracker/
PYTHONPATH=src python -m unittest discover tests -v

# Run live integration tests specifically
PYTHONPATH=src python -m unittest tests/test_live.py -v
```

### Testing Best Practices
- **Minimize Real API Calls**: When testing or benchmarking, always consider ways to reduce actual API calls to Spotify:
  - Use **cassette recording** (VCR-style mocking) to record API responses once and replay them for future test runs
  - Mock Spotify client for unit tests
  - Use fixed fixtures with pre-recorded data
  - See `benchmarks/cassette.py` for the cassette recording implementation
- **Style Preference**: Use **metal bands** for test data and examples whenever possible - it's our thing! 🤘
  - Examples: Metallica, Iron Maiden, Opeth, Gojira, Slayer, Mastodon, etc.
  - See `benchmarks/fixtures/` for curated metal artist lists
  - Keeps tests consistent, authentic, and appropriately heavy

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

## Performance

### Performance Notes

**Performance Metric**: We quantify application performance using a simple, objective metric:
- **# of Spotify API calls performed during the run**
- This is the primary performance indicator for all optimization work
- All benchmarks and performance discussions should reference this metric
- The profiler (`--profile` flag) tracks and reports API call counts by operation type

**Key Insight**: Spotify releases are **read-only** data - once published, they don't change. This makes them ideal for aggressive caching strategies.

**Current Bottlenecks**:
- Multiple API calls per artist (albums list → album tracks → track details)
- No persistent caching (every run re-fetches from API)
- ISRC lookups repeated across sessions
- Fixed 8-worker concurrency regardless of system capabilities

**Optimization Opportunities**: See `TODO.md` for detailed performance optimization plan with 6 phases prioritized by ROI.

### Performance Insights

This section documents interesting performance characteristics and insights discovered during development and optimization work.

#### Implemented Optimizations (2026-01-10)

**Phase 1: Persistent Release Caching** ✅
- Added SQLite-based caching for release data
- TTL-based expiration (24 hours default)
- **Expected Impact**: 80-90% reduction in API calls for repeat runs

**Phase 6: Smart Filtering** ✅
- Implemented early pagination stopping
- Stops fetching when albums before cutoff are encountered
- **Expected Impact**: 40-60% fewer API calls for prolific artists

**Phase 2: Persistent ISRC Cache** ✅
- Permanent cache for ISRC lookup results (immutable data)
- Eliminates redundant ISRC API searches across sessions
- **Expected Impact**: 50% reduction in ISRC API calls

**Instrumentation** ✅
- Added performance profiler with API call tracking
- Cache hit/miss rate monitoring
- Operation timing measurements
- Use `--profile` flag to see metrics

#### Usage
```bash
# First run (cold cache) - fetches from API
python main.py track --profile

# Second run (warm cache) - uses cached data
python main.py track --profile

# Force refresh (bypass cache)
python main.py track --force-refresh --profile
```

#### Baseline Metrics
*To be documented during testing*

#### Discoveries
- ISRC lookups were being repeated on every session despite being immutable
- **CRITICAL BUG FIXED (2026-01-10)**: Spotify does NOT return albums sorted chronologically
  - Albums are grouped by type: albums → singles → compilations
  - Early pagination stopping based on date caused missing recent singles that appeared after old albums
  - Fixed by continuing pagination through all pages while filtering individual albums by date
  - Regression test added: `TestSmartFilteringWithGroupedAlbums.test_finds_recent_singles_despite_old_albums_first`
- Most artists have <50 albums, but prolific artists benefit significantly from pagination optimization
- Release data caching provides the biggest performance win (80-90% API reduction)
