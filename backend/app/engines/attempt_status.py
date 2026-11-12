"""Canonical attempt statuses and their mapping to report buckets.

One attempt row maps to exactly one report bucket.  Keeping the mapping in one
place is what lets the report counts be reconciled item-by-item with the
attempt list instead of relying on independent counters.
"""

from __future__ import annotations

from typing import Iterable

SUCCESS = "success"
FAILED = "failed"
HARD_SKIPPED = "skipped_hard"
SOFT_DEGRADED = "degraded"

# Legacy status written by the pre-soft/hard implementation.
LEGACY_HARD_SKIPPED = "skipped_dep"

ALL_STATUSES = (SUCCESS, FAILED, HARD_SKIPPED, SOFT_DEGRADED, LEGACY_HARD_SKIPPED)

BUCKET_BY_STATUS: dict[str, str] = {
    SUCCESS: "succeeded",
    FAILED: "failed",
    HARD_SKIPPED: "hard_skipped",
    LEGACY_HARD_SKIPPED: "hard_skipped",
    SOFT_DEGRADED: "soft_degraded",
}

BUCKET_KEYS = ("succeeded", "failed", "hard_skipped", "soft_degraded", "other")

# Buckets whose jobs actually executed the fixture and produced output.
EXECUTED_BUCKETS = {"succeeded", "failed", "soft_degraded"}


def bucket_for(status: str) -> str:
    return BUCKET_BY_STATUS.get(status, "other")


def count_buckets(attempts: Iterable[dict]) -> dict[str, int]:
    counts = {key: 0 for key in BUCKET_KEYS}
    for attempt in attempts:
        counts[bucket_for(attempt["status"])] += 1
    return counts


def status_counts(attempts: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        counts[attempt["status"]] = counts.get(attempt["status"], 0) + 1
    return counts
