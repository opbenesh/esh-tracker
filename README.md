# 📡 Esh Tracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Agent Built](https://img.shields.io/badge/Built%20By-Agent-blueviolet)](AGENTS.md)

**Your personal radar for new Spotify releases.**
Track hundreds of artists, filter out the noise (re-releases, compilations), and never miss a drop.

## ⚡ Quick Start

```bash
pip install esh-tracker
```

**Track your favorite playlist:**
```bash
esh-tracker track 37i9dQZF1DWWOaP4H0w5b0
```

**Track a single artist:**
```bash
$ esh-tracker track --artist="Turnstile"

🎵 Turnstile - Dream Logic
   Album: Dream Logic - Single
   Released: 2025-11-14
   Type: single
   URL: https://open.spotify.com/...
```

## 🎮 What Cool Stuff Can I Do?

### 1. Build Your Own "Morning Metal" Digest
Don't rely on Spotify's algorithm. Set up a cron job to email yourself a daily list of releases from *only* the bands you actually care about.

```bash
# Runs daily at 9am, pipes clean TSV output to mail
0 9 * * * esh-tracker track <playlist-id> --days 1 --format pretty | mail -s "New Metal Drops" you@email.com
```

### 2. The "Curator" Workflow
Keep a single "Tracker" playlist on Spotify. Throw any artist's song in there to start tracking them. Remove it to stop.
*   **No cluttering your "Followed Artists" list.**
*   **Track 1,000+ bands effortlessly.**

### 3. Data Nerd Mode (JSON/TSV)
Pipe your release data into standard Unix tools or your own scripts.

```bash
# Find all releases by 'Turnstile' in your tracked list
esh-tracker track <playlist-id> --format tsv | grep -i "Turnstile"

# Export everything to JSON for your own dashboard
esh-tracker track --liked --format json > my_music_data.json
```

### 4. Time Travel
Missed a few months? Check what dropped in the last year.

```bash
# Catch up on 2025
esh-tracker track <playlist-id> --since 2025-01-01
```

### 5. Beat the Algorithm
Spotify's Release Radar **misses stuff**. It prioritizes big artists and often skips smaller bands or side projects.
*   **Zero Blindspots**: This tool checks the raw release feed for *everyone* you track.
*   **No "Algorithmic Sorting"**: You get a chronological list of exactly what came out. Period.

## ⚙️ Configuration

1.  **Get Credentials**: Grab a Client ID/Secret from the [Spotify Dashboard](https://developer.spotify.com/dashboard).
2.  **Set Environment**:
    ```bash
    export SPOTIPY_CLIENT_ID='your_id'
    export SPOTIPY_CLIENT_SECRET='your_secret'
    export SPOTIPY_REDIRECT_URI='http://localhost:8888/callback'
    ```

## 🤖 Agent-Built
> This tool was architected and written entirely by AI, with human oversight only for the cool metal band names.

[License](LICENSE) | [GitHub](https://github.com/opbenesh/esh-tracker)
