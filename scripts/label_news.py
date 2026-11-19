"""Create an auditable, independent news/publication label for the Enron test CSV.

The binary label denotes third-party published material (news articles, wire
stories, market bulletins, press releases, or copied analyst commentary), even
when forwarded by an Enron employee. It is separate from the accounting label.
The deterministic rules deliberately do not read Gemma predictions.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import re

SOURCE = Path("data/enron_labeled_curated_test.csv")
OUTPUT = Path("data/enron_labeled_curated_test_with_news.csv")
SOURCE_SHA256 = "96396a3e77be2bcd2295944ea20b0f8efc36c96c246596824e589e9ac84b796e"

# Row-level review of publication excerpts and rule/model disagreements. These
# labels describe the source of the text, not whether it discusses accounting.
# The source hash prevents these row IDs from silently attaching to new data.
REVIEWED_NEWS_ROWS = {
    5, 12, 14, 15, 18, 31, 41, 42, 46, 47, 51, 60, 67, 76, 78, 85,
    89, 96, 99, 105, 108, 111, 134, 136, 138, 162, 164, 174, 189,
    199, 223, 233, 234, 238, 248, 253, 260, 265, 273, 276, 284,
    297, 311, 316, 321, 322, 331, 338, 344, 349, 358, 363, 386,
    395, 401, 404, 408, 410, 414, 416, 417, 420, 446, 453, 456,
    457, 464, 469, 473, 483, 489, 493, 503, 508, 509, 513, 522,
    524, 526, 528, 530, 539, 546, 555,
}
REVIEWED_NOT_NEWS_ROWS = {
    11, 24, 27, 30, 101, 107, 157, 165, 175, 178, 196, 214, 232,
    242, 254, 307, 323, 357, 376, 384, 442, 481, 516, 536,
}

MARKERS = [
    ("wire_or_publication", re.compile(r"\b(?:Reuters(?: English News Service)?|Associated Press(?: Newswires)?|AP Business Writer|Dow Jones(?: Newswires)?|Bloomberg(?: News)?|AFX News|AFP-Extel|PR\s*Newswire|Business\s*Wire|Financial Times|Wall Street Journal|New York Times|Washington Post|Chicago Tribune|Houston Chronicle|Orlando Sentinel|BusinessWeek|Newsweek|MarketWatch(?:\.com)?|MSNBC|CNN|Salon\.com)\b", re.I)),
    ("publication_metadata", re.compile(r"(?:\bcopyright\s*[©?(]?\s*20\d\d\b|\b\(c\)\s*20\d\d\b|\bAll Rights Reserved\b|\b[A-Z][a-z]+\s+\d{1,2}\s*/?\s*\(?Reuters\)?\b|\bBy\s+[A-Z][a-z]+\s+[A-Z][a-z]+\s*(?:\n|,|AP Business Writer))", re.I)),
    ("market_bulletin", re.compile(r"(?:\b(?:Morning|Midday) Market View\b|\bRealMoney\.com'?s WEEKEND BULLETIN\b|\bMAJOR COMPANY\s*/\s*INDUSTRY NEWS\b|\bWilliams Energy News Live\b|\bGPCM News\b|\bWEO Newsletter\b|\bISDA PRESS REPORT\b)", re.I)),
]


def label_news(email: str) -> tuple[int, str]:
    """Return a reproducible rule label and the first matching evidence class."""
    for name, pattern in MARKERS:
        if pattern.search(email):
            return 1, name
    return 0, "no_publication_marker"


def build(source: Path = SOURCE, output: Path = OUTPUT) -> list[dict]:
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Source CSV changed; review row-level news annotations before rebuilding")
    with source.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"email", "label"}.issubset(rows[0]):
        raise ValueError("Expected labeled Enron email CSV")
    if REVIEWED_NEWS_ROWS & REVIEWED_NOT_NEWS_ROWS:
        raise ValueError("Conflicting reviewed news labels")
    for index, row in enumerate(rows):
        rule_label, basis = label_news(row["email"])
        if index in REVIEWED_NEWS_ROWS:
            row["news_label"], row["news_label_basis"] = 1, "reviewed_publication"
        elif index in REVIEWED_NOT_NEWS_ROWS:
            row["news_label"], row["news_label_basis"] = 0, "reviewed_non_publication"
        else:
            row["news_label"], row["news_label_basis"] = rule_label, basis
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*rows[0].keys()])
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    rows = build()
    print(f"Labeled {len(rows)} emails; news={sum(int(r['news_label']) for r in rows)}; saved {OUTPUT}")
