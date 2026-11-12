import json
from pathlib import Path

import pytest

from app.engines import attempt_status as st
from app.engines.dependency import (
    evaluate_dependencies,
    normalize_dependencies,
    normalize_dependency,
)
from app.engines.job_runner import run_fixture_job


def test_normalize_legacy_and_typed_edges():
    assert normalize_dependency("a") == {"name": "a", "kind": "hard"}
    assert normalize_dependency({"name": "b", "kind": "soft"}) == {
        "name": "b",
        "kind": "soft",
    }
    with pytest.raises(ValueError):
        normalize_dependency({"name": "c", "kind": "medium"})


def test_duplicate_edge_prefers_hard():
    edges = normalize_dependencies(
        [{"name": "a", "kind": "soft"}, {"name": "a", "kind": "hard"}]
    )
    assert edges == [{"name": "a", "kind": "hard"}]


def test_hard_missing_blocks():
    verdict = evaluate_dependencies(
        [{"name": "a", "kind": "hard"}], {"a": "failed"}
    )
    assert verdict["ready"] is False
    assert verdict["hard_blocked"] is True
    assert verdict["blocking"][0]["name"] == "a"


def test_soft_missing_allows_degraded_execution():
    verdict = evaluate_dependencies(
        [{"name": "a", "kind": "soft"}], {}
    )
    assert verdict["ready"] is True
    assert verdict["degraded_mode"] is True
    assert verdict["soft_missing"][0]["upstream_status"] == "not_run"


def test_soft_satisfied_is_not_degraded():
    verdict = evaluate_dependencies(
        [{"name": "a", "kind": "soft"}], {"a": "success"}
    )
    assert verdict["ready"] is True
    assert verdict["degraded_mode"] is False


def test_soft_does_not_mask_missing_hard():
    verdict = evaluate_dependencies(
        [{"name": "a", "kind": "soft"}, {"name": "b", "kind": "hard"}], {}
    )
    assert verdict["ready"] is False
    assert [x["name"] for x in verdict["blocking"]] == ["b"]


def test_fault_fixture_raises(tmp_path: Path):
    p = tmp_path / "fault.json"
    p.write_text(
        json.dumps({"watermark_ts": "2026-01-01T00:00:00Z", "rows": [], "fail": True}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        run_fixture_job(p)


def test_bucket_mapping_is_exhaustive_for_known_statuses():
    attempts = [
        {"status": st.SUCCESS},
        {"status": st.FAILED},
        {"status": st.HARD_SKIPPED},
        {"status": st.SOFT_DEGRADED},
        {"status": st.LEGACY_HARD_SKIPPED},
    ]
    buckets = st.count_buckets(attempts)
    assert buckets == {
        "succeeded": 1,
        "failed": 1,
        "hard_skipped": 2,
        "soft_degraded": 1,
        "other": 0,
    }
