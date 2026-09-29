"""
parse_sltda_pdfs.py

Extracts monthly total international tourist arrivals from SLTDA monthly
report PDFs (2019-2025) into a single clean CSV.

SLTDA changed their report wording several times over the years, so this
script tries several regex patterns per file, in order, and stops at the
first match. Anything that still fails is logged to a review CSV instead
of silently guessing a wrong number.

Usage:
    python src/etl/parse_sltda_pdfs.py --input "data/raw/sltda monthly 19-25" --output data/processed/sltda_arrivals.csv
"""

import argparse
import csv
import glob
import os
import re

import pdfplumber

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Ordered list of (pattern, group_index_for_number) tried against the
# concatenated text of the first ~3 pages of each report.
PATTERNS = [
    # "The total number of international tourist arrivals to Sri Lanka
    #  during April 2019 was 166,975."
    (re.compile(
        r"total number of international tourist arrivals to sri lanka "
        r"during [a-zA-Z]+,?\s*\d{4}\s*was\s*([\d,]+)", re.IGNORECASE), 1),
    # "April saw a decline in tourist arrivals, with 148,867 visitors"
    (re.compile(
        r"with\s+([\d,]{5,})\s+visitors", re.IGNORECASE), 1),
    # "Total arrivals until April reached 784,651" (year-to-date, NOT used
    # for monthly total, kept separate / not matched here on purpose)
    # Fallback: "X international tourist arrivals" near start of summary
    (re.compile(
        r"([\d,]{5,})\s+international tourist arrivals", re.IGNORECASE), 1),
]


def parse_filename(path):
    """Extract (year, month) from filename/folder, e.g. 'jan 19.pdf' or 'Apr 2024.pdf'."""
    base = os.path.basename(path).lower().replace(".pdf", "")
    folder_year = os.path.basename(os.path.dirname(path))
    m = re.match(r"([a-z]+)\s*(\d+)", base)
    if not m:
        return None, None
    mon_str, yr_str = m.group(1)[:3], m.group(2)
    month = MONTH_MAP.get(mon_str)
    if len(yr_str) == 4:
        year = int(yr_str)
    elif len(yr_str) == 2:
        year = 2000 + int(yr_str)
    else:
        year = int(folder_year) if folder_year.isdigit() else None
    return year, month


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def extract_from_table1(text, month):
    """Find the 'Table 1. Monthly tourist arrivals, <Month> <Year>' section and
    pull the current-year figure from that month's row.

    Rows can have 2 OR 3 year columns (some reports compare e.g. 2018 vs 2021
    vs 2022), so instead of assuming a fixed column count, this grabs every
    comma-grouped number token on the row and takes the LAST one -- the
    current report year's column is always rightmost among the arrival
    figures, before the %-change columns. Percent tokens (e.g. "21.8",
    "4,794.6%") are excluded by requiring no trailing '.' or '%'.
    """
    table_anchor = re.search(r"Table\s*1\.\s*Monthly tourist arrivals", text, re.IGNORECASE)
    if not table_anchor:
        return None
    # only search AFTER the table heading -- the month name appears many
    # other times on the page (section titles, maps, etc.) before this point
    text_after = text[table_anchor.end():]

    month_name = MONTH_NAMES[month - 1]
    # require the month name at the START of a line (the data row), not
    # mid-sentence -- otherwise this also matches the table's own title
    # line ("...Monthly tourist arrivals, April 2022")
    line_pattern = re.compile(rf"(?m)^{month_name}\b(.{{0,120}})", re.IGNORECASE)
    m = line_pattern.search(text_after)
    if not m:
        return None
    rest_of_line = m.group(1)

    # comma-grouped numbers only (>=1,000) -- excludes bare 1-3 digit % figures
    num_token = re.compile(r"\d{1,3}(?:,\s?\d{3})+")
    candidates = []
    for tok_match in num_token.finditer(rest_of_line):
        end = tok_match.end()
        # skip if immediately followed by '.' or '%' (i.e. it's a percent change value)
        trailing = rest_of_line[end:end + 2]
        if trailing.startswith(".") or trailing.startswith("%"):
            continue
        candidates.append(tok_match.group(0))

    if not candidates:
        return None

    raw = candidates[-1].replace(",", "").replace(" ", "")
    try:
        return int(raw)
    except ValueError:
        return None


def extract_total_arrivals(pdf_path, month):
    """Return (value:int|None, matched_pattern_index:str|None).

    Extracts one page at a time (instead of parsing several pages up front)
    and stops as soon as a pattern matches, since some pages (region maps)
    are graphic-heavy and slow to parse with pdfplumber -- no need to pay
    that cost once we already have our answer.
    """
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:6]:
            t = page.extract_text()
            if not t:
                continue
            text += t + "\n"

            # Try Table 1 row first -- most reliable across 2021-2026 formats
            val = extract_from_table1(text, month) if month else None
            if val is not None:
                return val, "table1_row"

            for idx, (pattern, group) in enumerate(PATTERNS):
                m = pattern.search(text)
                if m:
                    num_str = m.group(group).replace(",", "")
                    try:
                        return int(num_str), f"narrative_{idx}"
                    except ValueError:
                        continue
    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Root folder containing year subfolders of SLTDA PDFs")
    parser.add_argument("--output", required=True, help="Path to write the clean CSV")
    parser.add_argument("--review-output", default=None, help="Path to write rows that failed extraction")
    args = parser.parse_args()

    review_path = args.review_output or (os.path.splitext(args.output)[0] + "_needs_review.csv")

    pdf_files = sorted(glob.glob(os.path.join(args.input, "**", "*.pdf"), recursive=True))
    if not pdf_files:
        print(f"No PDFs found under {args.input}")
        return

    rows = []
    review_rows = []

    for path in pdf_files:
        year, month = parse_filename(path)
        total, pattern_idx = extract_total_arrivals(path, month)

        if total is None or year is None or month is None:
            review_rows.append({
                "file": path,
                "parsed_year": year,
                "parsed_month": month,
                "reason": "no pattern matched" if total is None else "filename parse failed",
            })
            continue

        rows.append({
            "year": year,
            "month": month,
            "total_arrivals": total,
            "source_file": os.path.basename(path),
            "matched_pattern": pattern_idx,
        })

    rows.sort(key=lambda r: (r["year"], r["month"]))

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["year", "month", "total_arrivals", "source_file", "matched_pattern"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Extracted {len(rows)} / {len(pdf_files)} months successfully -> {args.output}")

    if review_rows:
        with open(review_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "parsed_year", "parsed_month", "reason"])
            writer.writeheader()
            writer.writerows(review_rows)
        print(f"{len(review_rows)} file(s) need manual review -> {review_path}")
        for r in review_rows:
            print(f"  - {r['file']}  ({r['reason']})")


if __name__ == "__main__":
    main()
