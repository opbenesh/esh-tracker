# Agent Environment Notes

## Important Guidelines
- **IMPORTANT**: Use a TDD approach to solving problems. *Do not assume* that your solution is correct. Instead, *validate your solution is correct* by first creating a test case and running the test case to _prove_ the solution is working as intended.
- Assume your world knowledge is out of date. Use your web search tool to find up-to-date docs and information.
- When testing APIs, remember to test both mocks and live APIs.
- **IMPORTANT**: Whenever you discover something that you didn't know about this environment, about referenced APIs or used tools, append it to `agent.md`.
- **IMPORTANT**: If you want to perform experiments, put them in an `agent-experiments.py` file. Use separate methods for separate experiments and use `--` style args to run a specific experiment. Do not create additional files for experiments.
- **IMPORTANT**: Please maintain the `README.md` file after any significant changes to ensure documentation stays synchronized with the code.
- **IMPORTANT**: Commit and push changes after completing major features or refactoring steps to ensure work is backed up and synchronized.

## Project Overview for New Agents
### Architecture
- **Core Component**: `SpotifyReleaseTracker` (`src/artist_tracker/tracker.py`) orchestrates API calls and logic.
- **Persistence**: `ArtistDatabase` (`src/artist_tracker/database.py`) manages a SQLite database (`artists.db`) for storing artist IDs.
- **Entry Point**: `main.py` parses CLI args and dispatches commands.

### Key Workflows
1. **Tracking** (`track` command): Fetches recent albums for all artists in DB. Filters by 90-day window. Deduplicates using ISRC and exact name/date matching.
2. **Importing**: Can import from text files or Spotify playlists. Playlist import fetches *all* artists on the playlist.

### Common Pitfalls & Knowledge
- **Spotipy & Markets**: `sp.artist_albums` requires `country` parameter (e.g., 'US'). Other endpoints like `sp.track` use `market`. Mixing them up returns 404s or empty lists.
- **Rate Limiting**: The app handles 429 errors with exponential backoff. Do not remove this logic.
- **Sensitive Data**: Never commit `.env` or `artists.db`.

## Coding Guidelines
- **SOLID Principles**: Follow Single Responsibility, Open-Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion principles for maintainable and extensible code.
- **DRY (Don't Repeat Yourself)**: Avoid code duplication by extracting common logic into reusable functions, classes, or modules.
- **KISS (Keep It Simple, Stupid)**: Strive for simplicity in design and implementation. Avoid over-engineering.
- **Clean Code**: Write readable, self-documenting code with meaningful names, small functions, and clear structure.
- **Error Handling**: Implement robust error handling and logging to aid debugging and maintain reliability.
- **Performance**: Optimize for performance where necessary, but prioritize readability and maintainability.
- **Unix Philosophy**: Adhere to Unix design principles for CLI tools.
    - **Input**: Support standard input (stdin) for data ingestion where applicable (use `-` or detection).
    - **Output**: Separate data (stdout) from informational messages/logs (stderr). Success should often be silent or minimal.
    - **Composition**: Tools should be pipe-friendly.

## Tools & Dependencies
- **Python version**: Python 3.x
- **Package manager**: pip with `requirements.txt`
- **Dependencies**: spotipy, python-dotenv, tqdm
- **Dev dependencies**: mypy (in `requirements-dev.txt`)

## Running the Application
```bash
# Install dependencies first
pip install -r requirements.txt

# Run the tracker
python3 main.py [command]
```

## Testing
```bash
# Run all tests (unit + live integration)
PYTHONPATH=src python3 -m unittest discover tests -v

# Run live integration tests specifically
PYTHONPATH=src python3 -m unittest tests/test_live.py -v
```

## Configuration
- Credentials stored in `.env` file (git-ignored)
- Required env vars: `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`
