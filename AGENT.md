# Agent Notes

## Project

This repository builds a free-data Nasdaq bubble index. The compatible CLI entry
point is `nasdaq_bubble_index.py`, which delegates to the `bubble_index` package.
It can fetch public market data in live mode or use a deterministic offline
sample.

## Local Environment

- Python virtual environment: `.venv/`
- Install dependencies: `.venv/bin/python -m pip install -r requirements.txt`
- Current runtime used by the project: `.venv/bin/python`

## Run Commands

- Live data mode:
  `.venv/bin/python nasdaq_bubble_index.py`
- Offline smoke test:
  `.venv/bin/python nasdaq_bubble_index.py --offline-sample --out output_offline`
- Custom output directory:
  `.venv/bin/python nasdaq_bubble_index.py --out output`
- Debug logging:
  `.venv/bin/python nasdaq_bubble_index.py --offline-sample --log-level DEBUG`

## Code Layout

- `bubble_index/cli.py`: argument parsing and pipeline orchestration
- `bubble_index/data_sources.py`: FRED, Yahoo, FINRA, optional CSV, and offline data loading
- `bubble_index/scoring.py`: factor engineering and score calculation
- `bubble_index/reporting.py`: summary JSON, CSV output, and HTML rendering
- `bubble_index/factors.py`: factor metadata and value formatters
- `bubble_index/constants.py`: public data URLs and ticker lists
- `logging.conf`: default logging configuration

## Outputs

The script writes:

- `bubble_history.csv`
- `latest.json`
- `report.html`

Default output directory is `output/`.

## Notes For Future Agents

- Live mode depends on public network access to FRED, Yahoo Finance, and FINRA.
- If network access is unavailable, use `--offline-sample` to validate the full
  scoring and report generation pipeline locally.
- Keep changes scoped to `nasdaq_bubble_index.py` unless adding explicit project
  documentation or tests.
- This project is a research aid, not investment advice.
