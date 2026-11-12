from fastapi import APIRouter, HTTPException

from app.config import FIXTURES_DIR
from app.db import connect
from app.repositories import jobs as jobs_repo
from app.schemas.entities import (
    DependenciesBody,
    EnabledBody,
    FixtureBody,
    MaxAttemptsBody,
    as_plain_edges,
)

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs():
    conn = connect()
    try:
        return jobs_repo.list_jobs(conn)
    finally:
        conn.close()


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        return job
    finally:
        conn.close()


@router.put("/jobs/{job_id}/dependencies")
def put_dependencies(job_id: int, body: DependenciesBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        try:
            jobs_repo.update_dependencies(conn, job_id, as_plain_edges(body.dependencies))
            conn.commit()
        except jobs_repo.DependencyValidationError as exc:
            conn.rollback()
            raise HTTPException(422, str(exc)) from exc
        return jobs_repo.get_job(conn, job_id)
    finally:
        conn.close()


@router.patch("/jobs/{job_id}/max-attempts")
def patch_max_attempts(job_id: int, body: MaxAttemptsBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        jobs_repo.update_max_attempts(conn, job_id, body.max_attempts)
        conn.commit()
        return jobs_repo.get_job(conn, job_id)
    finally:
        conn.close()


@router.get("/fixtures")
def list_fixtures():
    """Fixture choices for the batch demo (success and fault variants)."""
    return sorted(p.name for p in FIXTURES_DIR.glob("*.json"))


@router.patch("/jobs/{job_id}/fixture")
def patch_fixture(job_id: int, body: FixtureBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        if not (FIXTURES_DIR / body.fixture_path).is_file():
            raise HTTPException(422, f"unknown fixture: {body.fixture_path}")
        jobs_repo.update_fixture_path(conn, job_id, body.fixture_path)
        conn.commit()
        return jobs_repo.get_job(conn, job_id)
    finally:
        conn.close()


@router.patch("/jobs/{job_id}/enabled")
def patch_enabled(job_id: int, body: EnabledBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        jobs_repo.update_enabled(conn, job_id, body.enabled)
        conn.commit()
        return jobs_repo.get_job(conn, job_id)
    finally:
        conn.close()
