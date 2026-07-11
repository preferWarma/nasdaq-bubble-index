"""Constants for report rendering."""

BUBBLE_STAGE_YEARS = (2007, 2018, 2020, 2021, 2022)
BUBBLE_STAGE_NOTES = {
    2007: "金融危机前夕",
    2018: "紧缩/科技股回撤",
    2020: "疫情冲击前",
    2021: "成长股泡沫",
    2022: "加息杀估值",
}
HISTORICAL_REFERENCE_STAGES = (
    (2000, "互联网泡沫"),
    *((year, BUBBLE_STAGE_NOTES[year]) for year in BUBBLE_STAGE_YEARS),
)
STATIC_ASSET_FILES = ("echarts.min.js",)
