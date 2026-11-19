"""Combine the two completed Gemma news-policy runs for recall-first triage."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.gemma4_openrouter import evaluate

DATA = Path("data")
EXCLUDE = DATA / "gemma4_exclude_test_predictions.csv"
INCLUDE = DATA / "gemma4_include_test_predictions.csv"
OUTPUT = DATA / "gemma4_union_test_predictions.csv"
METRICS = DATA / "gemma4_union_evaluation.json"
FIELDS = ["source_row", "label", "prediction", "exclude_prediction", "include_prediction", "truncated", "cost", "email_sha256"]


def read_results(path: Path) -> dict[int, dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = {int(row["source_row"]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate source rows in {path}")
    return result


def build(exclude: Path = EXCLUDE, include: Path = INCLUDE, output: Path = OUTPUT, metrics_path: Path = METRICS) -> dict:
    left, right = read_results(exclude), read_results(include)
    if not left or left.keys() != right.keys():
        raise ValueError("Both policy runs must contain the same completed source rows")
    combined = []
    for row_id in sorted(left):
        a, b = left[row_id], right[row_id]
        if a["label"] != b["label"] or a["email_sha256"] != b["email_sha256"]:
            raise ValueError(f"Runs disagree on label or email for row {row_id}")
        x, y = int(a["prediction"]), int(b["prediction"])
        combined.append({"source_row": row_id, "label": int(a["label"]), "prediction": max(x, y), "exclude_prediction": x, "include_prediction": y, "truncated": a["truncated"] == "True" or b["truncated"] == "True", "cost": float(a["cost"] or 0) + float(b["cost"] or 0), "email_sha256": a["email_sha256"]})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(combined)
    metrics = evaluate(combined)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
