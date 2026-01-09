# Agent Environment Notes

## Important Guidelines
- **IMPORTANT**: Use a TDD approach to solving problems. *Do not assume* that your solution is correct. Instead, *validate your solution is correct* by first creating a test case and running the test case to _prove_ the solution is working as intended.
- Assume your world knowledge is out of date. Use your web search tool to find up-to-date docs and information.
- When testing APIs, remember to test both mocks and live APIs.
- **IMPORTANT**: Whenever you discover something that you didn't know about this environment, about referenced APIs or used tools, append it to `agent.md`.
- **IMPORTANT**: If you want to perform experiments, put them in an `agent-experiments.py` file. Use separate methods for separate experiments and use `--` style args to run a specific experiment. Do not create additional files for experiments.
- **IMPORTANT**: Commit and push changes after completing major features or refactoring steps to ensure work is backed up and synchronized.

## Coding Guidelines
- **SOLID Principles**: Follow Single Responsibility, Open-Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion principles for maintainable and extensible code.
- **DRY (Don't Repeat Yourself)**: Avoid code duplication by extracting common logic into reusable functions, classes, or modules.
- **KISS (Keep It Simple, Stupid)**: Strive for simplicity in design and implementation. Avoid over-engineering.
- **Clean Code**: Write readable, self-documenting code with meaningful names, small functions, and clear structure.
- **Error Handling**: Implement robust error handling and logging to aid debugging and maintain reliability. Use low-cardinality logging with stable message strings e.g. `logger.info{id, foo}, 'Msg'`, `logger.error({error}, 'Another msg')`, etc
- **Performance**: Optimize for performance where necessary, but prioritize readability and maintainability.

## Tools & Dependencies
- **Python version**: `python3` (not `python`)
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

## API Knowledge
- **Spotify/Spotipy**:
    - `sp.artist_albums()` uses the `country` parameter, NOT `market`.
    - `sp.album_tracks()`, `sp.track()`, and `sp.playlist_tracks()` use the `market` parameter.
    - Many Spotify API endpoints are sensitive to regional restrictions; if a resource is not found (404), it might be due to the `market` or `country` filter being too restrictive or incorrect.
