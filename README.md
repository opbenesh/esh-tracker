# 🎵 Spotify Release Tracker

A specialized CLI tool to track, filter, and organize new releases (last 90 days) from your favorite Spotify artists.

Features ISRC-based deduplication, noise filtering (no karaoke/live/demos), and SQLite storage.

## 🚀 Quick Start
```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env and add SPOTIPY_CLIENT_ID & SPOTIPY_CLIENT_SECRET

# 3. Add artists & Track
python main.py import-playlist <playlist_id>
python main.py track
```

## 🛠️ Commands

| Command | Usage | Description |
|---|---|---|
| **track** | `python main.py track` | Fetch new releases for all tracked artists (default). |
| **import-playlist** | `python main.py import-playlist <id>` | Import all artists from a Spotify playlist. |
| **import-txt** | `python main.py import-txt <file>` | Import artists from a text file (names or URIs). |
| **list** | `python main.py list` | Show all artists in the database. |
| **remove** | `python main.py remove <name>` | Remove an artist by name or ID. |
| **export** | `python main.py export [file]` | Backup database to JSON. |
| **import-json** | `python main.py import-json <file>` | Restore from backup. |
| **debug-playlist** | `python main.py debug-playlist <url>` | One-time crawl of a playlist without saving. |

### options
- `--max-per-artist <N>`: Cap results per artist (ranked by popularity). Specific to `debug-playlist`.

## ✨ Features
- **90-Day Window**: Only fetches recent releases.
- **Smart Deduplication**: Uses ISRC to merge singles/albums.
- **Noise Filter**: Skips Live, Commentary, Karaoke, etc.
- **Popularity Ranking**: Prioritizes popular tracks.
- **Resilient**: Handles rate limits and API errors gracefully.


## 💻 Sample Interaction

First, register your favorite artists:

```bash
$ echo "Converge\nTurnstile" > artists.txt
$ python main.py import-txt artists.txt

================================================================================
IMPORT FROM TEXT FILE
================================================================================
Added: 2 artists
Skipped (already exists): 0 artists

Total artists in database: 2
================================================================================
```

Then, run the tracker to find their recent releases:

```
$ python main.py track

================================================================================
SPOTIFY RECENT RELEASE TRACKER
================================================================================
Cutoff Date: 2025-12-01 (90 days ago)
Total Artists in DB: 2
Total Releases Found: 2
Artists with Releases: 2
================================================================================

🎵 Converge - Atonement (Redux)
   Album: Atonement (single)
   Released: 2026-01-15
   ISRC: USUG11900199
   URL: https://open.spotify.com/track/4kbjBiBMv5dZ3eH78f9
   Popularity: 45

🎵 Turnstile - New Heart Design (Remix)
   Album: New Heart Design (single)
   Released: 2026-01-08
   ISRC: USCM52201235
   URL: https://open.spotify.com/track/67bNcGZpXF6rF5e9G8
   Popularity: 62
```

## ⚙️ Development

Development documentation can be found in `AGENT.md`.
