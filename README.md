# Spotify Recent Release Tracker

A Python tool to track recent releases (last 90 days) from your favorite Spotify artists. Features ISRC-based deduplication, noise filtering, concurrent processing, and SQLite database storage. Import artists from text files or Spotify playlists!

## Features

### Core Functionality
- **Release Tracking** — Fetches albums, singles, and compilations from the last 90 days
- **ISRC Deduplication** — Identifies and removes duplicate recordings using International Standard Recording Code
- **Noise Filtering** — Automatically skips Live, Remaster, Demo, Commentary, Instrumental, and Karaoke releases
- **Popularity Ranking** — Tracks include Spotify popularity scores (0-100) for prioritization

### Artist Management
- **SQLite Database** — Persistent storage with date added, name, and Spotify ID
- **Import from Text Files** — Add artists from `.txt` files with names or Spotify URIs
- **Import from Playlists** — Extract all artists from any Spotify playlist
- **Database Backup & Restore** — Export/import database to/from JSON files
- **Remove Artists** — Delete artists by name or Spotify ID

### One-Time Sessions
- **Debug Playlist Mode** — Track releases from a playlist without storing to database
- **Max Tracks per Artist** — Cap results per artist using popularity ranking

### Developer Experience
- **CLI Commands** — `import-txt`, `import-playlist`, `import-json`, `export`, `remove`, `list`, `track`, `debug-playlist`
- **Progress Bars** — Visual feedback with tqdm during long-running operations
- **Concurrent Processing** — Parallel artist processing using ThreadPoolExecutor
- **Retry Logic** — Exponential backoff for transient failures and rate limiting
- **Comprehensive Tests** — Unit tests with mocks + live integration tests against Spotify API

### Technical Details
- **Client Credentials Flow** — Server-to-server authentication (no browser login)
- **Environment Configuration** — Credentials loaded securely from `.env` file
- **Input Validation** — Validates Spotify IDs and artist names with detailed error messages
- **Custom Exceptions** — Specific exception types for better error handling
- **Type Hints** — Full type annotations throughout the codebase
- **Structured Logging** — Detailed logs written to `app.log`

## Installation

### Prerequisites
- Python 3.8 or higher
- Spotify Developer Account

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd artist-tracker
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Get Spotify API credentials:**
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new app
   - Copy your Client ID and Client Secret

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your credentials:
   ```
   SPOTIPY_CLIENT_ID=your_client_id_here
   SPOTIPY_CLIENT_SECRET=your_client_secret_here
   ```

## Usage

The tracker uses a SQLite database (`artists.db`) to store your tracked artists. You can manage artists using CLI commands.

### Quick Start

1. **Import artists from a text file:**

   Create a file `artists.txt` with artist names or Spotify URIs (one per line):
   ```
   Taylor Swift
   spotify:artist:06HL4z0CvFAxyc27GXpf02
   The Beatles
   Drake
   ```

   Then import:
   ```bash
   python spotify_tracker.py import-txt artists.txt
   ```

2. **Or import from a Spotify playlist:**

   ```bash
   python spotify_tracker.py import-playlist 37i9dQZF1DXcBWIGoYBM5M
   ```

   This will extract all artists featured in the playlist and add them to your database.

3. **List your tracked artists:**

   ```bash
   python spotify_tracker.py list
   ```

4. **Track recent releases:**

   ```bash
   python spotify_tracker.py track
   # or simply:
   python spotify_tracker.py
   ```

### CLI Commands

#### `import-txt <file>`
Import artists from a text file into the database.

```bash
python spotify_tracker.py import-txt artists.txt
```

The file supports:
- Plain artist names (e.g., "Taylor Swift")
- Spotify URIs (e.g., "spotify:artist:06HL4z0CvFAxyc27GXpf02")
- Comments (lines starting with #)
- Empty lines (ignored)

#### `import-playlist <playlist_id>`
Import all artists from a Spotify playlist.

```bash
# Using playlist ID
python spotify_tracker.py import-playlist 37i9dQZF1DXcBWIGoYBM5M

# Using Spotify URI
python spotify_tracker.py import-playlist spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
```

This extracts all unique artists featured in any track on the playlist.

#### `list`
Display all tracked artists in the database.

```bash
python spotify_tracker.py list
```

Shows:
- Artist name
- Date added
- Spotify artist ID

#### `track`
Track recent releases from all artists in the database (default command).

```bash
python spotify_tracker.py track
# or simply:
python spotify_tracker.py
```

The tracker will:
1. Load all artists from the database
2. Fetch releases from the last 90 days for each artist (with progress bar)
3. Remove duplicates using ISRC codes
4. Filter out noise (live versions, remasters, etc.)
5. Display results in the console
6. Log detailed information to `app.log`

#### `debug-playlist <playlist> [--max-per-artist N]`
One-time session: track releases from a playlist without storing to database.

```bash
# Basic usage
python spotify_tracker.py debug-playlist "https://open.spotify.com/playlist/6z5jMLEBI3t9sgQ3XDKOJ0"

# With max tracks per artist (uses popularity ranking)
python spotify_tracker.py debug-playlist "https://open.spotify.com/playlist/6z5jMLEBI3t9sgQ3XDKOJ0" --max-per-artist 5
```

Accepts:
- Playlist URLs (e.g., `https://open.spotify.com/playlist/...`)
- Playlist URIs (e.g., `spotify:playlist:...`)
- Playlist IDs (e.g., `6z5jMLEBI3t9sgQ3XDKOJ0`)

Output includes track popularity scores for each release.

#### `export [output_file]`
Export database to JSON backup file.

```bash
# Export to default file (artists_backup.json)
python spotify_tracker.py export

# Export to custom file
python spotify_tracker.py export my_backup.json
```

The exported JSON includes:
- Artist names
- Spotify artist IDs
- Date added timestamps

Perfect for backing up your database or transferring artists between machines.

#### `import-json <file>`
Import artists from a JSON backup file.

```bash
python spotify_tracker.py import-json artists_backup.json
```

This restores artists from a previously exported JSON backup. Artists that already exist in the database will be skipped.

#### `remove <identifier>`
Remove an artist from the database by name or Spotify ID.

```bash
# Remove by artist name (case-insensitive)
python spotify_tracker.py remove "Taylor Swift"

# Remove by Spotify artist ID
python spotify_tracker.py remove 06HL4z0CvFAxyc27GXpf02
```

The command will:
1. Try to match by Spotify ID first
2. If not found, search by artist name (case-insensitive)
3. Display confirmation of removal

### Output Examples

**Debug playlist (one-time session):**
```
================================================================================
ONE-TIME PLAYLIST SESSION (No data stored)
================================================================================
Artists in Playlist: 13
Artists with Releases: 11
Total Releases Found: 29
Max Tracks per Artist: 3
================================================================================

🎵 Megadeth - Let There Be Shred (pop: 63)
   Album: Let There Be Shred (single)
   Released: 2025-12-19
   ISRC: ITG272600074
   URL: https://open.spotify.com/track/18HAI5WUpc0f18ZpCDrPa0
```

**Import from text file:**
```
================================================================================
IMPORT FROM TEXT FILE
================================================================================
Added: 3 artists
Skipped (already exists): 1 artists

Total artists in database: 4
================================================================================
```

**List tracked artists:**
```
================================================================================
TRACKED ARTISTS
================================================================================
Total: 4 artists

  Taylor Swift
    Added: 2024-06-01 10:30
    Spotify ID: 06HL4z0CvFAxyc27GXpf02

  Ed Sheeran
    Added: 2024-06-01 10:30
    Spotify ID: 6eUKZXaKkcviH0Ku9w2n3V

================================================================================
```

**Track releases:**
```
================================================================================
SPOTIFY RECENT RELEASE TRACKER
================================================================================
Cutoff Date: 2024-03-03 (90 days ago)
Total Artists in DB: 4
Total Releases Found: 12
Artists with Releases: 3
================================================================================

🎵 Taylor Swift - Cruel Summer
   Album: Lover (album)
   Released: 2024-05-15
   ISRC: USUG11900198
   URL: https://open.spotify.com/track/1BxfuPKGuaTgP7aM0Bbdwr

🎵 Drake - Rich Flex
   Album: Her Loss (album)
   Released: 2024-04-20
   ISRC: USCM52201234
   URL: https://open.spotify.com/track/2Xr1dTzJee307cnzYjUcRZ

================================================================================
⚠️  MISSING ARTISTS (no results found)
================================================================================
  - Nonexistent Artist Name

Please check for typos or use Spotify artist URIs.
```

### Input Formats

Text files for importing support multiple formats:

```
# Comments start with #
# Empty lines are ignored

# Artist names (plain text)
Taylor Swift
The Beatles

# Spotify URIs
spotify:artist:06HL4z0CvFAxyc27GXpf02

# Spotify IDs also work
06HL4z0CvFAxyc27GXpf02
```

## Database Schema

The tracker uses SQLite to store tracked artists in `artists.db`:

```sql
CREATE TABLE artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_added TEXT NOT NULL,         -- ISO format timestamp
    artist_name TEXT NOT NULL,         -- Artist display name
    spotify_artist_id TEXT NOT NULL UNIQUE  -- Spotify artist ID (unique)
);
```

**Features:**
- **date_added**: Timestamp when the artist was added to the database
- **artist_name**: Display name of the artist
- **spotify_artist_id**: Unique Spotify artist ID (prevents duplicates)
- Indexed on `spotify_artist_id` for fast lookups

The database file is automatically excluded from git (in `.gitignore`).

## Development

### Running Tests

Run the test suite:
```bash
# Run unit tests (mocked API, no network calls)
python -m unittest test_spotify_tracker.py -v

# Run database tests
python -m unittest test_artist_database.py -v

# Run live integration tests (requires .env credentials)
python -m unittest test_spotify_tracker_live.py -v

# Run all tests
python -m unittest discover -v
```

### Test Coverage

The test suite includes:

**Unit Tests (32 tests)**
- Date parsing (full, partial, invalid)
- ISRC deduplication
- Noise filtering
- Artist search and ID parsing
- Playlist import with pagination
- Retry logic (server errors, rate limiting)
- Error handling

**Live Integration Tests (23 tests)**
- Real Spotify API calls
- Import from txt files
- Import from playlists (end-to-end)
- ISRC deduplication validation
- Noise filtering validation
- Error handling for invalid IDs

### Type Checking

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

Run mypy:
```bash
mypy spotify_tracker.py
```

### Test Coverage Report

Run with coverage:
```bash
pytest --cov=spotify_tracker test_spotify_tracker.py
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SPOTIPY_CLIENT_ID` | Yes | Your Spotify API Client ID |
| `SPOTIPY_CLIENT_SECRET` | Yes | Your Spotify API Client Secret |

### Customization

You can customize the tracker by modifying constants in `spotify_tracker.py`:

```python
class SpotifyReleaseTracker:
    # Noise filters
    NOISE_KEYWORDS = [
        'live', 'remaster', 'demo', 'commentary',
        'instrumental', 'karaoke'
    ]

    # Lookback window in days
    LOOKBACK_DAYS = 90
```

## How It Works

### 1. Authentication
Uses Spotify's Client Credentials Flow for server-to-server authentication (no user login required).

### 2. Artist Storage
- Stores tracked artists in SQLite database (`artists.db`)
- Schema: date_added, artist_name, spotify_artist_id
- Prevents duplicates using unique constraint on spotify_artist_id
- Import from text files or Spotify playlists

### 3. Artist Lookup
- Accepts both artist names and Spotify URIs
- Searches Spotify API for exact artist matches
- Stores artist ID and name in database
- Reports missing artists for manual correction

### 4. Release Discovery
- Fetches all albums, singles, and compilations
- Filters by release date (last 90 days)
- Retrieves track details from each release

### 5. Deduplication (ISRC)
Uses the International Standard Recording Code (ISRC) to identify duplicate recordings:
- Same song released as a single and on an album → kept once
- Different versions with different ISRCs → kept separately

### 6. Noise Filtering
Automatically skips releases containing:
- "Live" (live performances)
- "Remaster" (remastered versions)
- "Demo" (demo recordings)
- "Commentary" (audio commentary)
- "Instrumental" (instrumental versions)
- "Karaoke" (karaoke tracks)

### 7. Popularity Ranking
Each track includes a Spotify popularity score (0-100):
- Based on total plays and recency of plays
- Used for capping results with `--max-per-artist` option

### 8. Concurrent Processing
Uses ThreadPoolExecutor to process multiple artists in parallel for faster execution.

### 9. Error Handling & Retry Logic
The tracker implements robust error handling:
- **Exponential Backoff**: Retries failed requests with increasing delays (2s, 4s, 8s)
- **Rate Limit Handling**: Honors Spotify's `Retry-After` header for 429 responses
- **Custom Exceptions**: Specific exception types for validation, API errors, and rate limiting
- **Input Validation**: Validates Spotify IDs (exactly 22 alphanumeric characters) and artist names
- **Graceful Degradation**: Continues processing other artists if one fails

## Logging

Detailed logs are written to `app.log`:

```
2024-06-01 10:15:23 - INFO - Initialized tracker with cutoff date: 2024-03-03
2024-06-01 10:15:24 - INFO - Found artist 'Taylor Swift' (ID: 06HL4z0CvFAxyc27GXpf02)
2024-06-01 10:15:25 - INFO - Skipping 'Cruel Summer - Live' - contains noise keyword
2024-06-01 10:15:26 - INFO - Skipped track 'Love Story' because ISRC 'USCJY1031731' was already seen
2024-06-01 10:15:27 - INFO - Found 5 unique recent releases for 'Taylor Swift'
2024-06-01 10:15:28 - INFO - Capping 15 releases to top 5 by popularity for 'Artist Name'
```

## Troubleshooting

### "Missing Spotify credentials" Error
Ensure your `.env` file exists and contains valid credentials:
```bash
cat .env
```

### No Results for Artist
- Check for typos in artist names
- Try using the Spotify URI instead (find it on Spotify's artist page)
- Artist may not have releases in the last 90 days

### Rate Limiting
If you're tracking many artists, Spotify may rate limit your requests. The tool handles this gracefully with automatic retries.

## License

MIT License - feel free to use and modify as needed.

## Contributing

Contributions welcome! Please ensure:
1. All tests pass: `python -m unittest discover -v`
2. Type checking passes: `mypy spotify_tracker.py`
3. Code follows existing style conventions

## Acknowledgments

Built with:
- [Spotipy](https://spotipy.readthedocs.io/) - Spotify Web API Python library
- [python-dotenv](https://github.com/theskumar/python-dotenv) - Environment variable management
- [tqdm](https://github.com/tqdm/tqdm) - Progress bar library for better UX
