"""Constants for public data sources and index proxies."""

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
FINRA_MARGIN_XLSX_URL = (
    "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
)
YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    "?period1={period1}&period2={period2}&interval=1d&events=history"
)
MEGA_CAP_TICKERS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO")
