# 🎵 Spotify Release Tracker

Never miss a new release from your favorite artists. Track hundreds of bands, get notified of new music, and cut through the noise of re-releases and live albums.

## What It Does

This CLI tool watches your favorite Spotify artists and shows you their recent releases. It's designed for music fans who follow many artists and want to catch new releases without constantly checking Spotify.

**Perfect for**: Music fanatics tracking dozens of bands, playlist curators, music journalists, or anyone who's ever missed an album drop.

## ⚡ Quick Example

Here's what a typical session looks like:

```bash
# Check what's new from artists in a playlist (default: last 90 days)
$ python main.py track 37i9dQZF1DWWOaP4H0w5b0

================================================================================
SPOTIFY RECENT RELEASE TRACKER
================================================================================
Tracking 47 artists | Releases since 2025-10-11 (90 days)

🎵 Converge - Permanent Blue
   Album: The Dusk In Us (album)
   Released: 2025-12-18
   URL: https://open.spotify.com/track/5Z8K...

🎵 Meshuggah - Nostrum
   Album: Immutable (album)
   Released: 2026-01-03
   URL: https://open.spotify.com/track/3hB9...

🎵 Dillinger Escape Plan - Farewell, Mona Lisa
   Album: Option Paralysis (album)
   Released: 2025-11-22
   URL: https://open.spotify.com/track/7xYg...

================================================================================
Total releases: 3
================================================================================
```

That's it! You just discovered 3 new albums you might have missed.

## 🚀 Installation

**Prerequisites**: Python 3.7+, Spotify account (free)

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Get Spotify API credentials** (takes 2 minutes)

   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new app
   - Copy your Client ID and Client Secret

3. **Configure credentials**
   ```bash
   cp .env.example .env
   # Edit .env and paste your credentials
   ```

## 📖 How to Use

### Tracking Releases

**From a playlist** (primary workflow):
```bash
python main.py track <playlist-id>
```

**From multiple playlists**:
```bash
python main.py track <playlist-id-1> <playlist-id-2>
```

**From your "Liked Songs"**:
```bash
python main.py track --liked
```

**From a single artist**:
```bash
python main.py track --artist="Megadeth"
```

**Custom time range**:
```bash
# Last 30 days
python main.py track <playlist-id> --days 30

# Since a specific date
python main.py track <playlist-id> --since 2026-01-01
```

**Limit per artist** (useful for prolific bands):
```bash
# Get only the top 3 most popular tracks per artist
python main.py track <playlist-id> --max-per-artist 3
```

## 🎯 Output Formats

By default, the tool outputs a **human-readable pretty format**. You can change this to TSV, JSON, or CSV for piping to other tools.

```bash
# For piping
$ python main.py track <playlist-id> --format tsv
2026-01-15	Converge	Permanent Blue	The Dusk In Us	album	USDY41700501	https://...
```

**Other formats**:

| Format | Flag | Use Case |
|--------|------|----------|
| **Pretty** | `--format pretty` | Human-readable terminal output (default) |
| **TSV**    | `--format tsv`    | Pipe-friendly tab-separated values |
| **JSON**   | `--format json`   | Programmatic consumption |
| **CSV**    | `--format csv`    | Spreadsheet import |

## 💡 Pro Tips

### Daily Digest

Set up a cron job to email yourself daily (using TSV for clean output):
```bash
0 9 * * * python main.py track <playlist-id> --days 1 --format pretty | mail -s "New Metal Releases" you@email.com
```

### Filter by Artist

Use standard Unix tools to filter (using TSV for reliable parsing):
```bash
python main.py track <playlist-id> --format tsv | grep -i "converge"
```

## ❓ Troubleshooting

**"No credentials found"**: Make sure `.env` exists and has your Spotify credentials

**"Artist not found"**: Spotify search is spelling-sensitive.

**Empty results**: Your artists might not have released anything recently. Try `--days 365` for a broader search

**Rate limits**: The tool handles this automatically with backoff. Just be patient on first run with many artists.

## 🎸 Why This Tool Exists

If you follow metal, hardcore, or any genre with lots of artists, you know the pain:
- Checking Spotify manually every day is tedious
- Spotify's Release Radar misses stuff
- You follow 100+ bands and can't keep track
- Re-releases, live albums, and karaoke versions clutter everything

This tool solves that. It tracks everyone you care about, filters the noise, and gives you a clean list of actual new releases.

---

**Note**: This tool uses the Spotify Web API. Respect their [Terms of Service](https://www.spotify.com/legal/end-user-agreement/).
