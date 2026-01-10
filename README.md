# 🎵 Spotify Release Tracker

Never miss a new release from your favorite artists. Track hundreds of bands, get notified of new music, and cut through the noise of re-releases and live albums.

## What It Does

This CLI tool watches your favorite Spotify artists and shows you their recent releases. It's designed for music fans who follow many artists and want to catch new releases without constantly checking Spotify.

**Perfect for**: Music fanatics tracking dozens of bands, playlist curators, music journalists, or anyone who's ever missed an album drop.

## ⚡ Quick Example

### 1. Easy Use: Check One Artist

Want to quickly check if a band has something new?

```bash
$ spotify-tracker track --artist "Megadeth"

================================================================================
SPOTIFY RECENT RELEASE TRACKER
================================================================================
Tracking 1 artists | Releases since 2025-10-20 (90 days)

🎵 Megadeth - Let There Be Shred
   Album: Megadeth (album)
   Released: 2025-12-19
   URL: https://open.spotify.com/album/5xB...
```

### 2. Track from a Playlist (Recommended)

Keep all your favorite artists in one Spotify playlist. This is the most powerful way to use the tracker!

```bash
$ spotify-tracker track 37i9dQZF1DWWOaP4H0w5b0
```

**Why this is useful**: You can manage who you follow directly in Spotify. Add an artist's song to your "Tracker" playlist, and they are automatically tracked. Remove the song to stop tracking.

### 3. Track Your Liked Songs

If you use your "Liked Songs" library as your main collection:

```bash
$ spotify-tracker track --liked
```

## 🚀 Installation

**Prerequisites**: Python 3.7+, Spotify account (free tier is fine)

1. **Install the package**
   ```bash
   # Option A: Install from source
   pip install .
   
   # Option B: Install directly from GitHub
   pip install git+https://github.com/opbenesh/artist-tracker.git
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
spotify-tracker track <playlist-id>
```

**From multiple playlists**:
```bash
spotify-tracker track <playlist-id-1> <playlist-id-2>
```

**From your "Liked Songs"**:
```bash
spotify-tracker track --liked
```

**From a single artist**:
```bash
spotify-tracker track --artist="Megadeth"
```

**Custom time range**:
```bash
# Last 30 days
spotify-tracker track <playlist-id> --days 30

# Since a specific date
spotify-tracker track <playlist-id> --since 2026-01-01
```

**Limit per artist** (useful for prolific bands):
```bash
# Get only the top 3 most popular tracks per artist
spotify-tracker track <playlist-id> --max-per-artist 3
```

## 🎯 Output Formats

By default, the tool outputs a **human-readable pretty format**. You can change this to TSV, JSON, or CSV for piping to other tools.

```bash
# For piping
$ spotify-tracker track <playlist-id> --format tsv
2025-11-19	Converge	Love Is Not Enough	Love Is Not Enough	single	...	https://...
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
0 9 * * * spotify-tracker track <playlist-id> --days 1 --format pretty | mail -s "New Metal Releases" you@email.com
```

### Filter by Artist

Use standard Unix tools to filter (using TSV for reliable parsing):
```bash
spotify-tracker track <playlist-id> --format tsv | grep -i "converge"
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

🤖 **Agent-built** — Written entirely by AI. I just approved PRs and hardcoded metal band names into the tests.

**Note**: This tool uses the Spotify Web API. Respect their [Terms of Service](https://www.spotify.com/legal/end-user-agreement/).
