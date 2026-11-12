"""End-to-end orchestration tests: hard block vs soft degradation and counts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import db as db_module
from app.config import FIXTURES_DIR
from app.seed import init_db
from app.services import orchestrate_service as svc


@pytest.fixture()
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "app.db")
    init_db()
    yield tmp_path


def _set_job(conn, name: str, **fields) -> None:
    for key, value in fields.items():
        if key == "dependencies":
            value = json.dumps(value)
            key = "depends_on_json"
        conn.execute(f"UPDATE jobs SET {key}=? WHERE name=?", (value, name))
    conn.commit()


def _connect():
    return db_module.connect()


def _attempts_by_job(orch_id: int) -> dict[str, dict]:
    conn = _connect()
    try:
        rows = svc.orch_repo.list_attempts(conn, orch_id)
    finally:
        conn.close()
    return {row["job_name"]: row for row in rows}


def test_hard_block_skips_downstream_and_counts_match(fresh_db):
    conn = _connect()
    try:
        _set_job(conn, "ingest_orders", fixture_path="ingest_orders_fault.json")
    finally:
        conn.close()

    result = svc.run_orchestration()
    report = result["report"]

    attempts = _attempts_by_job(result["id"])
    assert attempts["ingest_orders"]["status"] == "failed"
    assert attempts["dim_customer"]["status"] == "success"
    assert attempts["fact_order_daily"]["status"] == "skipped_hard"
    detail = attempts["fact_order_daily"]["detail"]
    assert detail["blocked_by"][0]["name"] == "ingest_orders"

    assert report["failed"] == 1
    assert report["hard_skipped"] == 1
    assert report["succeeded"] == 1
    assert report["soft_degraded"] == 0
    assert report["attempt_count"] == 3
    assert report["reconciliation"]["balanced"] is True
    assert result["status"] == "partial"


def test_soft_dependency_missing_degrades_but_executes(fresh_db):
    conn = _connect()
    try:
        # dim_customer is disabled, so it produces no attempt in this run.
        _set_job(conn, "dim_customer", enabled=0)
        _set_job(
            conn,
            "fact_order_daily",
            dependencies=[
                {"name": "ingest_orders", "kind": "hard"},
                {"name": "dim_customer", "kind": "soft"},
            ],
        )
    finally:
        conn.close()

    result = svc.run_orchestration()
    report = result["report"]
    attempts = _attempts_by_job(result["id"])

    assert attempts["fact_order_daily"]["status"] == "degraded"
    detail = attempts["fact_order_daily"]["detail"]
    assert detail["degraded"] is True
    assert detail["soft_missing"][0]["name"] == "dim_customer"
    assert detail["soft_missing"][0]["upstream_status"] == "not_run"
    # The degraded job really ran.
    assert detail["result"]["artifact_rows"] == 1

    assert report["soft_degraded"] == 1
    assert report["hard_skipped"] == 0
    assert report["succeeded"] == 1  # only ingest_orders is a clean success
    assert report["failed"] == 0
    assert report["attempt_count"] == 2
    assert report["reconciliation"]["balanced"] is True
    assert result["status"] == "ok"


def test_watermark_only_reflects_clean_success(fresh_db):
    conn = _connect()
    try:
        _set_job(conn, "dim_customer", enabled=0)
        _set_job(
            conn,
            "fact_order_daily",
            dependencies=[{"name": "dim_customer", "kind": "soft"}],
        )
    finally:
        conn.close()

    svc.run_orchestration()

    conn = _connect()
    try:
        rows = {r["job_name"]: r for r in svc.wm_repo.list_watermarks(conn)}
    finally:
        conn.close()

    assert rows["ingest_orders"]["watermark_ts"] is not None
    assert rows["fact_order_daily"]["watermark_ts"] is None  # degraded, not promoted
    assert rows["dim_customer"]["watermark_ts"] is None  # disabled


def test_soft_dependency_on_failed_upstream_still_executes_degraded(fresh_db):
    conn = _connect()
    try:
        _set_job(conn, "ingest_orders", fixture_path="ingest_orders_fault.json")
        _set_job(
            conn,
            "fact_order_daily",
            dependencies=[
                {"name": "ingest_orders", "kind": "soft"},
                {"name": "dim_customer", "kind": "hard"},
            ],
        )
    finally:
        conn.close()

    result = svc.run_orchestration()
    attempts = _attempts_by_job(result["id"])
    assert attempts["ingest_orders"]["status"] == "failed"
    assert attempts["fact_order_daily"]["status"] == "degraded"


def test_reconcile_endpoint_matches_attempts(fresh_db):
    result = svc.run_orchestration()
    recon = svc.reconcile_orchestration(result["id"])
    assert recon["balanced"] is True
    assert recon["mismatches"] == []
    assert recon["recomputed"]["reconciliation"]["balanced"] is True


def test_soft_and_hard_same_layer_mixed_run(fresh_db):
    """One run containing success, soft degrade, failed and hard skip."""
    conn = _connect()
    try:
        _set_job(conn, "ingest_orders", fixture_path="ingest_orders_fault.json")
        _set_job(conn, "dim_customer", enabled=0)
        _set_job(
            conn,
            "fact_order_daily",
            dependencies=[
                {"name": "ingest_orders", "kind": "hard"},
                {"name": "dim_customer", "kind": "soft"},
            ],
        )
    finally:
        conn.close()

    result = svc.run_orchestration()
    report = result["report"]
    statuses = {
        row["job_name"]: row["status"]
        for row in svc.orch_repo.list_attempts(_connect(), result["id"])
    }
    assert statuses["ingest_orders"] == "failed"
    assert statuses["fact_order_daily"] == "skipped_hard"
    assert report["failed"] == 1
    assert report["hard_skipped"] == 1
    assert report["succeeded"] == 0
    assert report["soft_degraded"] == 0
    assert report["attempt_count"] == 2
    assert sum(
        report[k] for k in ("succeeded", "failed", "hard_skipped", "soft_degraded")
    ) == report["attempt_count"]
