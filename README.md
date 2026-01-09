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
| **track** | `python main.py track [-p]` | Fetch releases. Default is TSV. Use `-p` for pretty output. |
| **import-playlist** | `python main.py import-playlist <id>` | Import all artists from a Spotify playlist. |
| **import-txt** | `python main.py import-txt <file>` | Import artists from a text file (or `-` for stdin). |
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
$ printf "Converge\nTurnstile" | python main.py import-txt -
Added: 2, Skipped: 0
Total artists: 2
```


Then, run the tracker. By default, it outputs Tab-Separated Values (TSV) for easy processing:

```bash
$ python main.py track
2026-01-15	Converge	Atonement (Redux)	Atonement	single	USUG11900199	https://open.spotify.com/track/4kb...
2026-01-08	Turnstile	New Heart Design (Remix)	New Heart Design	single	USCM52201235	https://open.spotify.com/track/67b...
```

For human-readable output, use `--pretty`:

```bash
$ python main.py track --pretty

================================================================================
SPOTIFY RECENT RELEASE TRACKER
================================================================================
...
🎵 Converge - Atonement (Redux)
   Album: Atonement (single)
   Released: 2026-01-15
   ISRC: USUG11900199
   URL: https://open.spotify.com/track/4kbjBiBMv5dZ3eH78f9

🎵 Turnstile - New Heart Design (Remix)
   Album: New Heart Design (single)
   Released: 2026-01-08
   ISRC: USCM52201235
   URL: https://open.spotify.com/track/67bNcGZpXF6rF5e9G8
   Popularity: 62
```

## ⚙️ Development

Development documentation can be found in `AGENT.md`.
