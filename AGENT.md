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

## Performance Notes

**Key Insight**: Spotify releases are **read-only** data - once published, they don't change. This makes them ideal for aggressive caching strategies.

**Current Bottlenecks**:
- Multiple API calls per artist (albums list → album tracks → track details)
- No persistent caching (every run re-fetches from API)
- ISRC lookups repeated across sessions
- Fixed 8-worker concurrency regardless of system capabilities

**Optimization Opportunities**: See `TODO.md` for detailed performance optimization plan with 6 phases prioritized by ROI.

## Performance Insights

This section documents interesting performance characteristics and insights discovered during development and optimization work.

### Implemented Optimizations (2026-01-10)

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

### Usage
```bash
# First run (cold cache) - fetches from API
python main.py track --profile

# Second run (warm cache) - uses cached data
python main.py track --profile

# Force refresh (bypass cache)
python main.py track --force-refresh --profile
```

### Baseline Metrics
*To be documented during testing*

### Discoveries
- ISRC lookups were being repeated on every session despite being immutable
- Spotify returns albums sorted by release_date DESC, enabling early pagination stopping
- Most artists have <50 albums, but prolific artists benefit significantly from pagination optimization
- Release data caching provides the biggest performance win (80-90% API reduction)
