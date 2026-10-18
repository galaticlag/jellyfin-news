# Contributing

Issues and pull requests are welcome.

- Keep the project dependency-free (Python standard library only) and compatible with Python 3.11+.
- Run `ruff check . && ruff format --check .` and the test suite before opening a pull request:
  `PYTHONPATH=src python -m unittest discover -s tests`.
- Add or update tests for any behaviour change. Tests must run offline (use a fake TMDB client).
- Never commit credentials or local configuration (`config.toml`, `.env`).
- Document user-visible changes in `CHANGELOG.md`.
