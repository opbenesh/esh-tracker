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

```
$ python main.py track

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
```

## ⚙️ Development

Development documentation can be found in `AGENT.md`.
