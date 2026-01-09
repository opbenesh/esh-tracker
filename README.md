# Spotify Release Tracker

A command-line tool for tracking new music releases from your favorite Spotify artists. Never miss a release again.

## Overview

Spotify Release Tracker monitors your chosen artists and reports their recent releases. It filters noise (live recordings, karaoke, commentary), deduplicates tracks across singles and albums using ISRC codes, and outputs in machine-readable formats for easy automation.

**Built for Unix philosophy**: pipe-friendly, machine-readable by default, with human-readable options when needed.

## Key Features

- **Recent Release Tracking**: Configurable lookback window (default 90 days)
- **Smart Deduplication**: Uses ISRC codes to identify the same track across different releases
- **Noise Filtering**: Automatically excludes live recordings, karaoke, commentary, and other non-studio content
- **Multiple Output Formats**: TSV (default), JSON, CSV, and human-readable table formats
- **Flexible Date Ranges**: Query by days back or specific date ranges
- **Playlist Import**: Bulk import artists from any Spotify playlist
- **SQLite Storage**: Local database for fast queries and offline artist management
- **Resilient**: Handles API rate limits and transient errors gracefully

## Prerequisites

- Python 3.7 or higher
- Spotify Developer Account (free)
- Spotify API credentials (Client ID and Secret)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd artist-tracker
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Spotify API credentials**

   a. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)

   b. Create a new app (or use an existing one)

   c. Copy your Client ID and Client Secret

   d. Create a `.env` file in the project root:
   ```bash
   cp .env.example .env
   ```

   e. Edit `.env` and add your credentials:
   ```
   SPOTIPY_CLIENT_ID=your_client_id_here
   SPOTIPY_CLIENT_SECRET=your_client_secret_here
   ```

## Quick Start

```bash
# Import artists from a Spotify playlist
python main.py import-playlist <playlist_id>

# Or import from a text file (one artist name per line)
echo -e "Radiohead\nAphex Twin\nBoards of Canada" | python main.py import-txt -

# Track new releases (outputs TSV by default)
python main.py track

# View as human-readable table
python main.py track --format table
```

## Usage

### Basic Workflow

1. **Add artists** to your tracking database
2. **Run the tracker** to fetch recent releases
3. **Process the output** with standard Unix tools or consume programmatically

### Core Commands

#### `track` - Fetch New Releases

The primary command. Fetches and displays recent releases from all tracked artists.

```bash
# Default: TSV output of last 90 days
python main.py track

# Human-readable table format
python main.py track --format table

# JSON output for programmatic use
python main.py track --format json

# Custom date range
python main.py track --days 30
python main.py track --since 2026-01-01

# Limit tracks per artist (sorted by popularity)
python main.py track --max-per-artist 5
```

**Available Options:**

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--format` | `-f` | Output format: `tsv`, `json`, `csv`, or `table` | `tsv` |
| `--pretty` | `-p` | Shorthand for `--format table` (legacy) | - |
| `--days` | `-d` | Number of days to look back | `90` |
| `--since` | - | Start date in YYYY-MM-DD format (overrides `--days`) | - |
| `--max-per-artist` | `-m` | Maximum tracks per artist (by popularity) | unlimited |

#### `import-playlist` - Import Artists from Playlist

Import all artists from a Spotify playlist in one command.

```bash
# Import from a public or your own playlist
python main.py import-playlist <playlist_id>

# Example with full URL (ID extracted automatically)
python main.py import-playlist https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
```

The playlist ID is the string after `/playlist/` in the Spotify URL.

#### `import-txt` - Import Artists from Text File

Import artists from a text file or stdin. One artist name per line.

```bash
# From file
python main.py import-txt artists.txt

# From stdin (pipe or heredoc)
echo "Radiohead" | python main.py import-txt -
printf "Aphex Twin\nAutechre" | python main.py import-txt -

# From heredoc
python main.py import-txt - <<EOF
Nine Inch Nails
Massive Attack
Portishead
EOF
```

#### `list` - Show Tracked Artists

Display all artists currently in your tracking database.

```bash
python main.py list
```

#### `remove` - Remove an Artist

Remove an artist from tracking by name or Spotify ID.

```bash
# By name
python main.py remove "Radiohead"

# By Spotify ID
python main.py remove 4Z8W4fKeB5YxbusRsdQVPb
```

#### `stats` - Database Statistics

View statistics about your tracking database.

```bash
python main.py stats
```

Shows total artists tracked, current lookback window, database size, and more.

#### `export` - Backup Database

Export your artist database to JSON format.

```bash
# Export to file
python main.py export backup.json

# Export to stdout
python main.py export
```

#### `import-json` - Restore from Backup

Restore artists from a JSON backup.

```bash
python main.py import-json backup.json
```

#### `preview` - One-Time Playlist Preview

Preview releases from a playlist without adding artists to your database.

```bash
# Preview releases from a playlist
python main.py preview <playlist_url_or_id>

# With track limit per artist
python main.py preview <playlist_url_or_id> --max-per-artist 3
```

## Output Formats

### TSV (Tab-Separated Values) - Default

Machine-readable format, ideal for piping to other tools or importing into spreadsheets.

```bash
$ python main.py track
2026-01-15	Radiohead	Burn the Witch	A Moon Shaped Pool	single	GBUM71600501	https://open.spotify.com/track/...
2026-01-10	Aphex Twin	Blackbox Life Recorder	...	album	GBAHT2100301	https://open.spotify.com/track/...
```

**Columns**: Date, Artist, Track, Album, Album Type, ISRC, URL, [Popularity]

### JSON

Structured data for programmatic consumption.

```bash
$ python main.py track --format json
{
  "releases": [
    {
      "artist": "Radiohead",
      "track": "Burn the Witch",
      "album": "A Moon Shaped Pool",
      "album_type": "single",
      "release_date": "2026-01-15",
      "isrc": "GBUM71600501",
      "url": "https://open.spotify.com/track/...",
      "popularity": 75
    }
  ],
  "meta": {
    "total": 2,
    "cutoff_date": "2025-10-17",
    "artists_tracked": 15
  }
}
```

### CSV

Comma-separated values with headers.

```bash
$ python main.py track --format csv
date,artist,track,album,album_type,isrc,url,popularity
2026-01-15,Radiohead,Burn the Witch,A Moon Shaped Pool,single,GBUM71600501,https://...,75
```

### Table (Human-Readable)

Formatted output for terminal viewing.

```bash
$ python main.py track --format table

================================================================================
SPOTIFY RECENT RELEASE TRACKER
================================================================================
Tracking 15 artists | Releases since 2025-10-17 (90 days)

🎵 Radiohead - Burn the Witch
   Album: A Moon Shaped Pool (single)
   Released: 2026-01-15
   ISRC: GBUM71600501
   URL: https://open.spotify.com/track/...
   Popularity: 75

🎵 Aphex Twin - Blackbox Life Recorder
   Album: ... (album)
   Released: 2026-01-10
   ISRC: GBAHT2100301
   URL: https://open.spotify.com/track/...
   Popularity: 68

================================================================================
Total releases: 2
================================================================================
```

## Examples

### Daily Automation

Get today's releases and email yourself:

```bash
#!/bin/bash
python main.py track --days 1 --format table | mail -s "New Music Today" you@example.com
```

### Filter Specific Artists

Use grep to filter TSV output:

```bash
python main.py track | grep -i "radiohead"
```

### Top Tracks Only

Get the most popular release per artist:

```bash
python main.py track --max-per-artist 1 --format csv > top_tracks.csv
```

### Import from Multiple Playlists

```bash
for playlist_id in 37i9dQZF1DXcBWIGoYBM5M 37i9dQZF1DX0XUsuxWHRQd; do
  python main.py import-playlist $playlist_id
done
```

### Weekly Digest

```bash
# Run weekly via cron
0 9 * * MON python main.py track --days 7 --format table > /tmp/weekly_releases.txt
```

## Troubleshooting

### "No credentials found"

Ensure your `.env` file exists in the project root and contains valid `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET`.

### "Invalid client"

Your Spotify API credentials are incorrect. Verify them in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

### Rate limiting / 429 errors

The tool automatically handles rate limits with exponential backoff. For large artist lists, the initial run may take some time.

### "Artist not found"

Spotify's search is case-insensitive but sensitive to spelling. Try variations of the artist name, or use `import-playlist` to ensure exact matches.

### Empty results

- Check that artists are actually in your database: `python main.py list`
- Verify the date range: `python main.py track --days 365` for a broader search
- Some artists may not have released music recently

### Database locked

If you get "database is locked" errors, ensure no other instance of the tool is running. SQLite doesn't support concurrent writes.

## Development

For development guidelines, architecture documentation, and contribution information, see [AGENT.md](AGENT.md).

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
PYTHONPATH=src python3 -m unittest discover tests -v

# Run live integration tests (requires valid .env credentials)
PYTHONPATH=src python3 -m unittest tests/test_live.py -v
```

### Type Checking

```bash
mypy src/
```

## Project Structure

```
artist-tracker/
├── main.py                  # CLI entry point
├── src/
│   └── artist_tracker/
│       ├── tracker.py       # Core tracking logic
│       ├── database.py      # SQLite persistence
│       └── ...
├── tests/                   # Unit and integration tests
├── requirements.txt         # Runtime dependencies
├── requirements-dev.txt     # Development dependencies
├── .env.example            # Template for credentials
└── README.md               # This file
```

## License

[Specify your license here, e.g., MIT, Apache 2.0, etc.]

## Contributing

Contributions are welcome! Please see [AGENT.md](AGENT.md) for coding guidelines and development setup.

---

**Note**: This tool uses the Spotify Web API. Respect Spotify's [Terms of Service](https://www.spotify.com/legal/end-user-agreement/) and rate limits.
