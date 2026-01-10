# 🎵 Spotify Release Tracker

Never miss a new release from your favorite artists. Track hundreds of bands, get notified of new music, and cut through the noise of re-releases and live albums.

## What It Does

This CLI tool watches your favorite Spotify artists and shows you their recent releases. It's designed for music fans who follow many artists and want to catch new releases without constantly checking Spotify.

**Perfect for**: Metal fans tracking dozens of bands, playlist curators, music journalists, or anyone who's ever missed an album drop.

## ⚡ Quick Example

Here's what a typical session looks like:

```bash
# Add your favorite artists from a playlist
$ python main.py import-playlist 37i9dQZF1DWWOaP4H0w5b0
Imported 47 artists from "Heavy Metal Classics"

# Check what's new (default: last 90 days)
$ python main.py track --format table

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

### Adding Artists

**From a Spotify playlist** (easiest way):
```bash
python main.py import-playlist <playlist_id>
```

**From a text file**:
```bash
# One artist per line
echo -e "Converge\nTurnstile\nCode Orange" > artists.txt
python main.py import-txt artists.txt

# Or pipe directly
echo "Meshuggah" | python main.py import-txt -
```

### Tracking Releases

**Basic tracking** (shows last 90 days):
```bash
python main.py track
```

**Human-readable format**:
```bash
python main.py track --format table
```

**Custom time range**:
```bash
# Last 30 days
python main.py track --days 30

# Since a specific date
python main.py track --since 2026-01-01
```

**Limit per artist** (useful for prolific bands):
```bash
# Get only the top 3 most popular tracks per artist
python main.py track --max-per-artist 3 --format table
```

### Managing Your List

**See all tracked artists**:
```bash
python main.py list
```

**Remove an artist**:
```bash
python main.py remove "Converge"
```

**Get stats**:
```bash
python main.py stats
```

## 🎯 Output Formats

By default, the tool outputs **TSV** (tab-separated values) - perfect for piping to other tools or importing into spreadsheets:

```bash
$ python main.py track
2026-01-15	Converge	Permanent Blue	The Dusk In Us	album	USDY41700501	https://...
2026-01-10	Meshuggah	Nostrum	Immutable	album	SEAN52201145	https://...
```

**Other formats**:

| Format | Flag | Use Case |
|--------|------|----------|
| **Table** | `--format table` or `-p` | Human-readable terminal output |
| **JSON** | `--format json` | Programmatic consumption |
| **CSV** | `--format csv` | Spreadsheet import |

## 💡 Pro Tips

### Daily Digest

Set up a cron job to email yourself daily:
```bash
0 9 * * * python main.py track --days 1 --format table | mail -s "New Metal Releases" you@email.com
```

### Filter by Artist

Use standard Unix tools to filter:
```bash
python main.py track | grep -i "converge"
```

### One-Time Preview

Want to check a playlist without adding all artists to your database?
```bash
python main.py preview <playlist_url>
```

## ❓ Troubleshooting

**"No credentials found"**: Make sure `.env` exists and has your Spotify credentials

**"Artist not found"**: Spotify search is spelling-sensitive. Try using `import-playlist` to get exact matches

**Empty results**: Your artists might not have released anything recently. Try `--days 365` for a broader search

**Rate limits**: The tool handles this automatically with backoff. Just be patient on first run with many artists.

## 🎸 Why This Tool Exists

If you follow metal, hardcore, or any genre with lots of artists, you know the pain:
- Checking Spotify manually every day is tedious
- Spotify's Release Radar misses stuff
- You follow 100+ bands and can't keep track
- Re-releases, live albums, and karaoke versions clutter everything

This tool solves that. It tracks everyone you care about, filters the noise, and gives you a clean list of actual new releases.

## 📁 Project Structure

```
artist-tracker/
├── main.py                  # CLI entry point
├── src/artist_tracker/      # Core application code
├── tests/                   # Test suite
├── requirements.txt         # Dependencies
└── .env.example            # Credentials template
```

---

**Note**: This tool uses the Spotify Web API. Respect their [Terms of Service](https://www.spotify.com/legal/end-user-agreement/).
