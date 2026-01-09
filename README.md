# Spotify Recent Release Tracker

A Python tool to track recent releases (last 90 days) from your favorite Spotify artists. Features ISRC-based deduplication, noise filtering, concurrent processing, and SQLite database storage. Import artists from text files or Spotify playlists!

## Features

### Hard Requirements
- ✅ **Client Credentials Flow**: Uses Spotify's Client Credentials authentication (no browser login required)
- ✅ **Environment Configuration**: Loads credentials securely from `.env` file
- ✅ **ISRC Deduplication**: Identifies and removes duplicate recordings using International Standard Recording Code

### Additional Features
- ✅ **SQLite Database Storage**: Stores tracked artists with date added, name, and Spotify ID
- ✅ **Import from Text Files**: Add artists from text files with names or Spotify URIs
- ✅ **Import from Playlists**: Extract and track all artists from any Spotify playlist
- ✅ **CLI Commands**: Easy-to-use commands (import-txt, import-playlist, list, track)
- ✅ **Concurrent Processing**: Processes multiple artists in parallel using ThreadPoolExecutor
- ✅ **90-Day Lookback**: Strict date filtering for releases within the last 90 days
- ✅ **Partial Date Handling**: Handles year-only and year-month dates (defaults to January 1st)
- ✅ **Regional Filtering**: Filters results for Israel market (`IL`) to show only playable tracks
- ✅ **Noise Filtering**: Automatically skips Live, Remaster, Demo, Commentary, Instrumental, and Karaoke releases
- ✅ **Mixed Input Support**: Accepts both artist names and Spotify URIs (`spotify:artist:...`)
- ✅ **Missing Artist Detection**: Reports artists that returned no results
- ✅ **Type Hints**: Full type annotations for better code quality
- ✅ **Structured Logging**: Detailed logs written to `app.log`
- ✅ **Comprehensive Tests**: Unit tests with mocked API (zero network calls)

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
2. Fetch releases from the last 90 days for each artist
3. Remove duplicates using ISRC codes
4. Filter out noise (live versions, remasters, etc.)
5. Display results in the console
6. Log detailed information to `app.log`

### Output Examples

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
python -m unittest test_spotify_tracker.py -v
```

All tests use mocked Spotify API - no network calls are made.

### Type Checking

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

Run mypy:
```bash
mypy spotify_tracker.py
```

### Test Coverage

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

    # Market for regional filtering
    MARKET = 'IL'

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

### 7. Concurrent Processing
Uses ThreadPoolExecutor to process multiple artists in parallel for faster execution.

## Logging

Detailed logs are written to `app.log`:

```
2024-06-01 10:15:23 - INFO - Initialized tracker with cutoff date: 2024-03-03
2024-06-01 10:15:24 - INFO - Found artist 'Taylor Swift' (ID: 06HL4z0CvFAxyc27GXpf02)
2024-06-01 10:15:25 - INFO - Skipping 'Cruel Summer - Live' - contains noise keyword
2024-06-01 10:15:26 - INFO - Skipped track 'Love Story' because ISRC 'USCJY1031731' was already seen
2024-06-01 10:15:27 - INFO - Found 5 unique recent releases for 'Taylor Swift'
```

## Testing Strategy

The test suite includes:

### Zero Network Tests
All tests use `unittest.mock` to mock the Spotify client - no real API requests occur.

### Deterministic Time
Tests mock `datetime` to a fixed date (2024-06-01) for reproducible results.

### Boundary Testing
Specific test cases verify the 90-day boundary:
- Input: Date `2024-03-03` (90 days ago) → Result: **KEEP** ✅
- Input: Date `2024-03-02` (91 days ago) → Result: **DISCARD** ❌

### Coverage
- Date parsing (full, partial, invalid)
- ISRC deduplication
- Noise filtering
- Artist search and ID parsing
- Concurrent processing
- Missing file handling

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
If you're tracking many artists, Spotify may rate limit your requests. The tool handles this gracefully and will log errors.

## License

MIT License - feel free to use and modify as needed.

## Contributing

Contributions welcome! Please ensure:
1. All tests pass: `python -m unittest test_spotify_tracker.py`
2. Type checking passes: `mypy spotify_tracker.py`
3. Code follows existing style conventions

## Acknowledgments

Built with:
- [Spotipy](https://spotipy.readthedocs.io/) - Spotify Web API Python library
- [python-dotenv](https://github.com/theskumar/python-dotenv) - Environment variable management
