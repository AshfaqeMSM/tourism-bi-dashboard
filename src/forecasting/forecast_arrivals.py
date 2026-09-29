"""
forecast_arrivals.py

Builds a monthly tourist-arrivals forecast for Sri Lanka using Prophet,
with historical shock periods (Easter attacks 2019, COVID border closure
2020-21, economic crisis 2022) flagged as regressors rather than predicted.

Input:
  - data/processed/sltda_arrivals.csv        (year, month, total_arrivals)
  - data/processed/sltda_arrivals_needs_review.csv (months the ETL script
    couldn't auto-extract -- see KNOWN_ZERO_MONTHS / notes below)

Output:
  - data/processed/arrivals_forecast.csv      (historical + forecast, monthly)
  - data/processed/arrivals_forecast_plot.png (quick visual check)

IMPORTANT: this script fills in the known COVID-closure months (borders shut
18 Mar 2020 through most of 2021) with 0, since SLTDA's own reports confirm
near-zero arrivals in that window even though the ETL script couldn't parse
an exact number from the narrative text. A handful of OTHER review-flagged
months (e.g. Jan/Feb 2022, Jul 2024, May 2025) are NOT known to be zero --
those are just extraction misses, and are filled by linear interpolation
here as a placeholder. Replace KNOWN_ZERO_MONTHS / re-run once you've
manually filled in the real numbers from the review CSV for full accuracy.

Usage:
    python src/forecasting/forecast_arrivals.py \
        --arrivals data/processed/sltda_arrivals.csv \
        --output data/processed/arrivals_forecast.csv \
        --periods 12
"""

import argparse
import os

import pandas as pd
from prophet import Prophet

# Months confirmed near-zero due to Sri Lanka's border closure (18 Mar 2020
# through most of 2021). Update this list if you get exact SLTDA figures.
KNOWN_ZERO_MONTHS = {
    (2020, 4), (2020, 5), (2020, 6), (2020, 7), (2020, 8),
    (2020, 9), (2020, 10), (2020, 11), (2020, 12),
    (2021, 8), (2021, 9), (2021, 10), (2021, 11), (2021, 12),
}

# Historical shock windows used as a binary regressor (NOT predicted forward)
SHOCK_WINDOWS = [
    ("2019-04-01", "2019-12-31"),  # Easter Sunday attacks, Apr 2019
    ("2020-03-18", "2021-12-31"),  # COVID border closure + slow reopening
    ("2022-01-01", "2023-06-30"),  # Economic crisis (fuel/forex shortages, 49.7% inflation in 2022)
]


def build_monthly_series(arrivals_path):
    df = pd.read_csv(arrivals_path)
    df["date"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))

    full_range = pd.date_range(df["date"].min(), df["date"].max(), freq="MS")
    full = pd.DataFrame({"date": full_range})
    full = full.merge(df[["date", "total_arrivals"]], on="date", how="left")

    # Fill known-zero COVID months explicitly
    for y, m in KNOWN_ZERO_MONTHS:
        mask = (full["date"].dt.year == y) & (full["date"].dt.month == m)
        full.loc[mask & full["total_arrivals"].isna(), "total_arrivals"] = 0

    still_missing = full["total_arrivals"].isna().sum()
    if still_missing:
        print(f"NOTE: {still_missing} month(s) still missing after zero-fill -- "
              f"interpolating linearly as a placeholder. Fill these in from "
              f"sltda_arrivals_needs_review.csv for real accuracy:")
        print(full.loc[full["total_arrivals"].isna(), "date"].dt.strftime("%Y-%m").tolist())
        full["total_arrivals"] = full["total_arrivals"].interpolate()

    return full


def add_shock_flag(df):
    df["shock_period"] = 0
    for start, end in SHOCK_WINDOWS:
        mask = (df["date"] >= start) & (df["date"] <= end)
        df.loc[mask, "shock_period"] = 1
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arrivals", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--periods", type=int, default=12, help="Months to forecast forward")
    args = parser.parse_args()

    monthly = build_monthly_series(args.arrivals)
    monthly = add_shock_flag(monthly)

    prophet_df = monthly.rename(columns={"date": "ds", "total_arrivals": "y"})

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
    )
    model.add_regressor("shock_period")
    model.fit(prophet_df[["ds", "y", "shock_period"]])

    future = model.make_future_dataframe(periods=args.periods, freq="MS")
    # Assume no new shocks in the forecast horizon (we are not predicting future shocks)
    future = future.merge(monthly[["date", "shock_period"]].rename(columns={"date": "ds"}), on="ds", how="left")
    future["shock_period"] = future["shock_period"].fillna(0)

    forecast = model.predict(future)

    out = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].merge(
        prophet_df[["ds", "y"]], on="ds", how="left"
    )
    out = out.rename(columns={"ds": "date", "y": "actual_arrivals",
                               "yhat": "forecast_arrivals",
                               "yhat_lower": "forecast_lower", "yhat_upper": "forecast_upper"})
    out[["forecast_arrivals", "forecast_lower", "forecast_upper"]] = out[
        ["forecast_arrivals", "forecast_lower", "forecast_upper"]
    ].clip(lower=0)
    # Arrivals are whole people, not fractions -- Prophet outputs a smooth
    # continuous curve, so round to the nearest integer for display/use.
    out[["forecast_arrivals", "forecast_lower", "forecast_upper"]] = out[
        ["forecast_arrivals", "forecast_lower", "forecast_upper"]
    ].round(0).astype("Int64")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"\nWrote {len(out)} months (history + {args.periods}-month forecast) -> {args.output}")

    plot_path = os.path.splitext(args.output)[0] + "_plot.png"
    fig = model.plot(forecast)
    fig.savefig(plot_path, dpi=120)
    print(f"Saved plot -> {plot_path}")


if __name__ == "__main__":
    main()
