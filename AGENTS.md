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
- Weight optimization:
  `.venv/bin/python nasdaq_bubble_index.py --optimize-weights --weight-search-trials 3000`

## Code Layout

- `bubble_index/cli.py`: argument parsing and pipeline orchestration
- `bubble_index/data_sources.py`: FRED, Yahoo, FINRA, optional CSV, and offline data loading
- `bubble_index/scoring.py`: factor engineering and score calculation
- `bubble_index/factors.py`: 6 grouped factor definitions, display text, and configured weights
- `bubble_index/backtesting.py`: future drawdown and historical stage backtest summaries
- `bubble_index/weight_optimization.py`: random search plus walk-forward validation for group weights
- `bubble_index/reporting.py`: compatibility facade that re-exports reporting helpers
- `bubble_index/report/`: report rendering package
  - `assets.py`: static asset copying for generated reports
  - `charts.py`: static SVG helpers plus local ECharts payload/bootstrap
  - `constants.py`: historical stage and static asset constants
  - `formatting.py`: score, percent, number, and JSON formatting helpers
  - `gauge.py`: SVG score gauge rendering
  - `html.py`: full HTML page template
  - `outputs.py`: `write_outputs()` orchestration
  - `sections.py`: historical reference and backtest HTML sections
  - `summary.py`: latest-score summary helpers
  - `time_series.py`: chart/date/index series utilities
- `bubble_index/logging_config.py`: logging setup
- `bubble_index/constants.py`: public data URLs and ticker lists
- `config/factor_weights.json`: default optimized 6-group factor weights
- `config/logging.conf`: default logging configuration
- `static/echarts.min.js`: vendored Apache ECharts runtime used by `report.html`
- `.github/workflows/deploy-pages.yml`: GitHub Pages build and deploy workflow

Default CLI settings use `--start 1986-01-01` and `--window-years 20`, so the
report can annotate 2007 and later historical bubble-stage coordinates.

## Outputs

The script writes to the selected output directory:

- `bubble_history.csv`
- `latest.json`
- `backtest_summary.json`
- `report.html`
- `static/echarts.min.js`

Default output directory is `output/`. Generated output directories are ignored
by git; `static/echarts.min.js` is a source asset and should be committed.

## Reporting Notes

- The report uses local ECharts, not a CDN. Keep `static/echarts.min.js` and
  `copy_static_assets()` in sync.
- The bubble score chart and index chart share the same visible date window.
  `dataZoom` events are manually synchronized between charts.
- The date range inputs and the ECharts drag/zoom controls are also
  bidirectionally synchronized; keep both paths wired to the same zoom state.
- Y axes are recalculated from the visible range after zooming so local movement
  remains readable. Full-range bubble score view stays anchored to `0-100`.
- Special stage explanations live below the chart as chips to avoid label
  overlap on dense years such as 2020-2022.
- Factor cards show the bottom-level indicators active for the current score.
  Candidate indicators, public-data sources, and fallback calculations live in
  a compact disclosure section; keep this metadata aligned with `scoring.py`.
- The header refresh button only cache-busts and reloads the latest deployed
  HTML. It does not fetch market data in the browser; data refresh still happens
  through the Python pipeline or GitHub Actions.

## GitHub Pages

- The Pages workflow builds `site/`, copies `report.html` to `index.html`, and
  deploys the generated artifact.
- GitHub Actions cron is UTC. The current schedule is `30 2 * * 2-6`, which is
  Beijing time Tuesday-Saturday 10:30, leaving public sources more time to
  update the previous US trading day.

## Maintenance Rules

- When changing code structure, config locations, generated outputs, workflow
  behavior, or report assets, update this `AGENTS.md` along with user-facing
  docs such as `README.md` when relevant.
- Do not leave stale path references. Use `rg` for moved files and config names.
- Prefer an offline smoke test before finishing:
  `.venv/bin/python nasdaq_bubble_index.py --offline-sample --out output_smoke`
- Also run syntax checks after Python changes:
  `.venv/bin/python -m compileall bubble_index nasdaq_bubble_index.py`
- This project is a research aid, not investment advice.
