"""
parse_worldbank_xls.py

Extracts Sri Lanka's yearly values from World Bank indicator .xls exports
(GDP growth, inflation, tourism receipts, population) and merges them into
a single clean CSV: one row per year, one column per indicator.

World Bank export format: sheet "Data", header row is row index 3
(0-indexed), columns = Country Name, Country Code, Indicator Name,
Indicator Code, then one column per year.

Usage:
    python src/etl/parse_worldbank_xls.py --input data/raw/worldbank --output data/processed/worldbank_sri_lanka.csv
"""

import argparse
import glob
import os

import pandas as pd

COUNTRY_NAME = "Sri Lanka"

# Maps a keyword found in the filename -> a short, clean column name.
FILE_KEYWORDS = {
    "gdp growth": "gdp_growth_pct",
    "inflation": "inflation_pct",
    "tourism, receipts": "tourism_receipts_usd",
    "population": "population_total",
}


def clean_column_name(filename):
    lower = filename.lower()
    for keyword, col_name in FILE_KEYWORDS.items():
        if keyword in lower:
            return col_name
    # fallback: slugify the filename
    base = os.path.splitext(filename)[0]
    return base.lower().replace(" ", "_").replace(",", "").replace("(", "").replace(")", "").replace("%", "pct")


def extract_country_series(path, column_name):
    """Return a DataFrame with columns [year, <column_name>] for Sri Lanka."""
    df = pd.read_excel(path, sheet_name="Data", header=3)
    row = df[df["Country Name"] == COUNTRY_NAME]
    if row.empty:
        print(f"  WARNING: '{COUNTRY_NAME}' not found in {os.path.basename(path)}")
        return pd.DataFrame(columns=["year", column_name])

    row = row.iloc[0]
    year_cols = [c for c in df.columns if str(c).isdigit()]
    records = []
    for year_col in year_cols:
        val = row[year_col]
        if pd.notna(val):
            records.append({"year": int(year_col), column_name: val})
    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Folder containing the World Bank .xls files")
    parser.add_argument("--output", required=True, help="Path to write the merged yearly CSV")
    parser.add_argument("--start-year", type=int, default=2015, help="Earliest year to keep (default 2015)")
    args = parser.parse_args()

    xls_files = sorted(glob.glob(os.path.join(args.input, "*.xls")))
    if not xls_files:
        print(f"No .xls files found in {args.input}")
        return

    merged = None
    for path in xls_files:
        filename = os.path.basename(path)
        column_name = clean_column_name(filename)
        print(f"Parsing {filename} -> column '{column_name}'")
        series_df = extract_country_series(path, column_name)
        merged = series_df if merged is None else merged.merge(series_df, on="year", how="outer")

    merged = merged[merged["year"] >= args.start_year].sort_values("year").reset_index(drop=True)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    merged.to_csv(args.output, index=False)
    print(f"\nWrote {len(merged)} years x {len(merged.columns) - 1} indicators -> {args.output}")
    print(merged.to_string(index=False))


if __name__ == "__main__":
    main()
