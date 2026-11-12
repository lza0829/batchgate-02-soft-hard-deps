from __future__ import annotations

from typing import Any

from app.config import FIXTURES_DIR
from app.db import connect
from app.engines import attempt_status as st
from app.engines.dependency import evaluate_dependencies, topological_layers
from app.engines.job_runner import run_fixture_job
from app.repositories import jobs as jobs_repo
from app.repositories import orchestrations as orch_repo
from app.repositories import watermarks as wm_repo


def _reconcile(report: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the report counts *from* the recorded attempts and check them.

    The report never carries independently incremented counters: every bucket is
    derived from attempt rows, so the displayed totals always match the list.
    """
    buckets = st.count_buckets(attempts)
    executed = sum(buckets[key] for key in st.EXECUTED_BUCKETS)
    reconciliation = {
        "attempt_count": len(attempts),
        "status_counts": st.status_counts(attempts),
        "buckets": buckets,
        "executed": executed,
        "balanced": (
            sum(buckets.values()) == len(attempts)
            and buckets["succeeded"] + buckets["failed"]
            + buckets["hard_skipped"] + buckets["soft_degraded"] == len(attempts)
        ),
    }
    report.update(
        {
            "succeeded": buckets["succeeded"],
            "failed": buckets["failed"],
            "hard_skipped": buckets["hard_skipped"],
            "soft_degraded": buckets["soft_degraded"],
            "executed": executed,
            "attempt_count": len(attempts),
            "reconciliation": reconciliation,
        }
    )
    return report


def dashboard_stats() -> dict[str, Any]:
    conn = connect()
    try:
        return {
            "job_count": conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"],
            "enabled_jobs": conn.execute(
                "SELECT COUNT(*) c FROM jobs WHERE enabled=1"
            ).fetchone()["c"],
            "orchestration_count": conn.execute(
                "SELECT COUNT(*) c FROM orchestrations"
            ).fetchone()["c"],
            "attempt_count": conn.execute(
                "SELECT COUNT(*) c FROM job_attempts"
            ).fetchone()["c"],
            "watermarked_jobs": conn.execute(
                "SELECT COUNT(*) c FROM watermarks WHERE watermark_ts IS NOT NULL"
            ).fetchone()["c"],
        }
    finally:
        conn.close()


def run_orchestration() -> dict[str, Any]:
    conn = connect()
    try:
        jobs = [j for j in jobs_repo.list_jobs(conn) if j["enabled"]]
        orch_id = orch_repo.create_orchestration(conn)
        # Upstream state observed *within this orchestration*.
        upstream_states: dict[str, str] = {}
        watermarked_in_run = 0
        layers = topological_layers(jobs)

        def record(job: dict[str, Any], status: str, detail: dict[str, Any]) -> None:
            detail.setdefault("degraded", False)
            detail.setdefault("soft_missing", [])
            detail.setdefault("job", job["name"])
            orch_repo.insert_attempt(
                conn,
                orchestration_id=orch_id,
                job_id=job["id"],
                attempt_no=1,
                status=status,
                detail=detail,
            )

        def mark_upstream(job: dict[str, Any], state: str) -> None:
            upstream_states[job["name"]] = state

        for layer in layers:
            for job in layer:
                verdict = evaluate_dependencies(job["dependencies"], upstream_states)
                if not verdict["ready"]:
                    record(
                        job,
                        st.HARD_SKIPPED,
                        {
                            "reason": verdict["reason"],
                            "blocked_by": verdict["blocking"],
                            "soft_missing": verdict["soft_missing"],
                            "dependency_mode": "hard",
                        },
                    )
                    mark_upstream(job, "blocked")
                    continue

                try:
                    result = run_fixture_job(FIXTURES_DIR / job["fixture_path"])
                except Exception as exc:  # noqa: BLE001
                    record(
                        job,
                        st.FAILED,
                        {
                            "error": str(exc),
                            "soft_missing": verdict["soft_missing"],
                            "degraded": verdict["degraded_mode"],
                        },
                    )
                    mark_upstream(job, "failed")
                    continue

                if verdict["degraded_mode"]:
                    record(
                        job,
                        st.SOFT_DEGRADED,
                        {
                            "reason": verdict["reason"],
                            "soft_missing": verdict["soft_missing"],
                            "degraded": True,
                            "dependency_mode": "soft",
                            "result": result,
                        },
                    )
                else:
                    record(job, st.SUCCESS, result)

                # Only a genuinely successful execution promotes the watermark.
                # A soft-degraded run is recorded in the attempt list with its
                # result, but its possibly incomplete output must not become the
                # authoritative watermark shown on the watermark page.
                if not verdict["degraded_mode"]:
                    wm_repo.set_watermark(
                        conn, job["id"], result["watermark_ts"], result["artifact_rows"]
                    )
                    watermarked_in_run += 1
                    mark_upstream(job, "success")
                else:
                    # Degraded output is not a clean success: a downstream *hard*
                    # edge still blocks, while a downstream *soft* edge degrades.
                    mark_upstream(job, "degraded")

        attempts = orch_repo.list_attempts(conn, orch_id)
        report: dict[str, Any] = {
            "orchestration_id": orch_id,
            "job_total": len(jobs),
            "watermarked_in_run": watermarked_in_run,
            "layer_count": len(layers),
        }
        _reconcile(report, attempts)
        # Failed or hard-blocked runs are partial; soft degradation is still "ok"
        # because every runnable job produced output.
        status = "ok" if report["failed"] == 0 and report["hard_skipped"] == 0 else "partial"
        orch_repo.finish_orchestration(conn, orch_id, status, report)
        conn.commit()
        return orch_repo.get_orchestration(conn, orch_id) or report
    finally:
        conn.close()


def reconcile_orchestration(orch_id: int) -> dict[str, Any] | None:
    """Recompute report buckets from attempts, exposing any stored mismatch."""
    conn = connect()
    try:
        row = orch_repo.get_orchestration(conn, orch_id)
        if row is None:
            return None
        attempts = orch_repo.list_attempts(conn, orch_id)
        stored = row["report"] or {}
        recomputed = _reconcile({}, attempts)
        mismatches = []
        for key in ("succeeded", "failed", "hard_skipped", "soft_degraded", "attempt_count"):
            if key in stored and stored.get(key) != recomputed.get(key):
                mismatches.append(
                    {"field": key, "report": stored.get(key), "attempts": recomputed.get(key)}
                )
        return {
            "orchestration_id": orch_id,
            "stored_report": stored,
            "recomputed": recomputed,
            "mismatches": mismatches,
            "balanced": not mismatches and recomputed["reconciliation"]["balanced"],
        }
    finally:
        conn.close()
