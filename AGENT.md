# Agent Notes

## Project

This repository builds a free-data Nasdaq bubble index. The main entry point is
`nasdaq_bubble_index.py`, which can fetch public market data in live mode or use
a deterministic offline sample.

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
