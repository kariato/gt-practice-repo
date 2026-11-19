"""OpenRouter Jev decision classifier for the curated Enron email data.

This is a zero-shot classifier: Jev is queried with a typed yes/no question.
No model weights are trained, and labels are used only to evaluate predictions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import random
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
MAX_EMAIL_CHARS = 20_000

QUESTION = {
    "type": "noul",
    "instructions": (
        "Does this email contain substantive evidence or discussion of Enron "
        "accounting irregularities, misleading financial reporting, improper "
        "mark-to-market valuation, concealment of losses, or misuse of special "
        "purpose entities such as the Raptors? Judge the email content, not "
        "the sender or search phrase."
    ),
    "criteria": {
        "true": (
            "The email substantively discusses or documents one of those Enron "
            "accounting concerns, including a relevant news report, allegation, "
            "internal concern, or description of the practice."
        ),
        "false": (
            "The email is unrelated, or only mentions finance or accounting in a "
            "routine way without a substantive Enron irregularity concern."
        ),
    },
}

OUTPUT_FIELDS = [
    "source_row", "label", "prediction", "probability", "truncated",
    "model", "request_id", "input_tokens", "cost", "email_sha256", "config_sha256",
]


def load_labeled_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not {"email", "label"}.issubset(reader.fieldnames or []):
            raise ValueError("Expected 'email' and 'label' columns")
        rows = []
        for index, record in enumerate(reader):
            if record["label"] not in {"0", "1"}:
                raise ValueError(f"Unexpected label in row {index}: {record['label']!r}")
            rows.append({"source_row": index, "email": record["email"], "label": int(record["label"])})
    return rows


def sample_rows(rows: list[dict], limit: int | None, seed: int = 42) -> list[dict]:
    if limit is None or limit >= len(rows):
        return rows
    if limit < 1:
        raise ValueError("limit must be positive or None")
    return sorted(random.Random(seed).sample(rows, limit), key=lambda row: row["source_row"])


def config_hash(model: str, max_email_chars: int) -> str:
    config = {"model": model, "max_email_chars": max_email_chars, "question": QUESTION}
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def classify_email(email: str, api_key: str, model: str = MODEL,
                   max_email_chars: int = MAX_EMAIL_CHARS) -> dict:
    """Return Jev's probability of the positive class and request metadata."""
    if not api_key:
        raise ValueError("Set OPENROUTER_API_KEY before calling Jev")
    if max_email_chars < 1:
        raise ValueError("max_email_chars must be positive")

    truncated = len(email) > max_email_chars
    state = {"email": email[:max_email_chars]}
    payload = {"model": model, "state": state, "questions": {"relevant": QUESTION}}
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                result = json.load(response)
            break
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 524, 529} or attempt == 3:
                raise RuntimeError(f"OpenRouter returned HTTP {error.code}; see account or API status") from error
            retry_after = error.headers.get("Retry-After")
            delay = min(30, float(retry_after)) if retry_after and retry_after.isdigit() else 2 ** attempt
            time.sleep(delay)

    answer = result.get("answers", {}).get("relevant", {})
    probability = answer.get("noul")
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise ValueError(f"Jev returned no numeric 'noul' answer: {answer!r}")
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError(f"Jev returned an invalid probability: {probability!r}")
    usage = result.get("usage") or {}
    return {
        "probability": float(probability),
        "prediction": int(probability >= 0.5),
        "truncated": truncated,
        "model": result.get("model", model),
        "request_id": result.get("id", ""),
        "input_tokens": usage.get("input_tokens", ""),
        "cost": usage.get("cost", ""),
    }


def run_classifier(rows: list[dict], output_path: Path, api_key: str,
                   model: str = MODEL, max_email_chars: int = MAX_EMAIL_CHARS) -> list[dict]:
    """Append predictions after each request; reruns skip matching completed rows."""
    fingerprint = config_hash(model, max_email_chars)
    previous = {}
    if output_path.exists():
        with output_path.open(newline="", encoding="utf-8") as handle:
            for result in csv.DictReader(handle):
                for field in ("source_row", "label", "prediction"):
                    result[field] = int(result[field])
                result["probability"] = float(result["probability"])
                result["truncated"] = result["truncated"].lower() == "true"
                if result["input_tokens"]:
                    result["input_tokens"] = int(result["input_tokens"])
                if result["cost"]:
                    result["cost"] = float(result["cost"])
                previous[int(result["source_row"])] = result

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        for position, row in enumerate(rows, start=1):
            row_id = row["source_row"]
            email_hash = hashlib.sha256(row["email"].encode("utf-8")).hexdigest()
            if row_id in previous:
                saved = previous[row_id]
                if saved["email_sha256"] != email_hash or saved["config_sha256"] != fingerprint:
                    raise ValueError(f"Saved prediction for row {row_id} uses different input or settings")
                continue
            decision = classify_email(row["email"], api_key, model, max_email_chars)
            result = {
                "source_row": row_id,
                "label": row["label"],
                **decision,
                "email_sha256": email_hash,
                "config_sha256": fingerprint,
            }
            writer.writerow(result)
            handle.flush()
            previous[row_id] = result
            if position % 10 == 0:
                print(f"Processed {position}/{len(rows)} selected rows", flush=True)
    return [previous[row["source_row"]] for row in rows]


def evaluate(results: list[dict]) -> dict:
    if not results:
        raise ValueError("No predictions to evaluate")
    tp = tn = fp = fn = 0
    for row in results:
        truth, pred = int(row["label"]), int(row["prediction"])
        tp += truth == 1 and pred == 1
        tn += truth == 0 and pred == 0
        fp += truth == 0 and pred == 1
        fn += truth == 1 and pred == 0
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "rows": len(results), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": (tp + tn) / len(results),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "truncated": sum(str(row["truncated"]).lower() == "true" for row in results),
        "total_cost_usd": sum(float(row["cost"] or 0) for row in results),
    }
