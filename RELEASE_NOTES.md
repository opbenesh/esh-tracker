# 📡 Esh Tracker v0.1.0: Initial Release

**"The Algorithm can take a hike."**

We are thrilled to announce the first public release of **Esh Tracker**, the CLI tool for music nerds who want to track their favorite artists without relying on Spotify's patchy "Release Radar".

## 🌟 Key Features

### 🎧 Zero Blindspots
*   **Track Everything**: Monitors your playlists, "Liked Songs", or specific artists for *every single release*.
*   **Smart Filtering**: Automatically hides "Live", "Remaster", "Demo", and "Commentary" clutter so you only see fresh music.
*   **ISRC De-duplication**: Intelligent logic detects when a single is re-released on an album and correctly identifies the *original* drop date.

### 🛠️ Data Nerd Mode
Pipe your music data into your own scripts or spreadsheets with flexible output formats:
*   `--format pretty`: Beautiful, human-readable CLI output (default).
*   `--format tsv`: Tab-Separated Values for grep/awk piping.
*   `--format json`: Full metadata export.
*   `--format csv`: For spreadsheet lovers.
*   **[NEW]** `--format ids`: Output raw `spotify:track:ID` list—paste directly into a Spotify playlist (Ctrl+C / Ctrl+V)!

### ⚡ Power User Tools
*   `--since <date>`: Time travel back to catch up on what you missed.
*   `--days <n>`: Custom lookback windows.
*   `--max-per-artist <n>`: Cap the output for prolific artists using popularity ranking.

## 📦 Installation

```bash
pip install esh-tracker
```

## 🚀 Quick Start

```bash
# Track a single artist
esh-tracker track --artist="Turnstile"

# Use your Release Radar as a source (but better filtered)
esh-tracker track 37i9dQZF1DWWOaP4H0w5b0
```

---
*Built with ❤️ (and 🤖) by Agent.*
