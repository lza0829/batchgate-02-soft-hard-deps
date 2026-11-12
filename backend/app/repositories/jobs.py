from __future__ import annotations

import json
from typing import Any

import sqlite3

from app.engines.dependency import (
    dependency_names,
    normalize_dependencies,
    normalize_dependency,
)


def _decode_depends(raw: str | None) -> list[dict[str, str]]:
    """Decode stored dependencies, upgrading legacy plain-name lists."""
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid depends_on_json: {raw!r}") from exc
    return normalize_dependencies(payload)


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    d["dependencies"] = _decode_depends(d.pop("depends_on_json"))
    d["depends_on"] = dependency_names(d["dependencies"])
    d["enabled"] = bool(d["enabled"])
    return d


_SELECT = (
    "SELECT id, name, fixture_path, depends_on_json, max_attempts, enabled, note FROM jobs"
)


def list_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(f"{_SELECT} ORDER BY id").fetchall()
    return [_row(r) for r in rows]  # type: ignore[misc]


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    r = conn.execute(f"{_SELECT} WHERE id=?", (job_id,)).fetchone()
    return _row(r)


def get_job_by_name(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    r = conn.execute(f"{_SELECT} WHERE name=?", (name,)).fetchone()
    return _row(r)


def update_max_attempts(conn: sqlite3.Connection, job_id: int, max_attempts: int) -> None:
    conn.execute("UPDATE jobs SET max_attempts=? WHERE id=?", (max_attempts, job_id))


def update_enabled(conn: sqlite3.Connection, job_id: int, enabled: bool) -> None:
    conn.execute("UPDATE jobs SET enabled=? WHERE id=?", (1 if enabled else 0, job_id))


def update_fixture_path(conn: sqlite3.Connection, job_id: int, fixture_path: str) -> None:
    conn.execute("UPDATE jobs SET fixture_path=? WHERE id=?", (fixture_path, job_id))


class DependencyValidationError(ValueError):
    """Raised when a dependency edge set is invalid."""


def _assert_no_cycle(conn: sqlite3.Connection, job_id: int, edges: list[dict[str, str]]) -> None:
    names = {
        row["name"]: int(row["id"])
        for row in conn.execute("SELECT id, name FROM jobs").fetchall()
    }
    graph: dict[int, list[int]] = {job_id_value: [] for job_id_value in names.values()}
    for row in conn.execute("SELECT id, depends_on_json FROM jobs").fetchall():
        deps = _decode_depends(row["depends_on_json"])
        graph[int(row["id"])] = [names[e["name"]] for e in deps if e["name"] in names]
    # Apply the proposed edge set before walking for cycles.
    graph[job_id] = [names[e["name"]] for e in edges if e["name"] in names]

    visiting: set[int] = set()
    visited: set[int] = set()

    def walk(node: int) -> None:
        if node in visiting:
            raise DependencyValidationError("dependency graph would contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for nxt in graph.get(node, []):
            walk(nxt)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        walk(node)


def update_dependencies(
    conn: sqlite3.Connection, job_id: int, dependencies: list[Any]
) -> list[dict[str, str]]:
    """Replace a job's dependency edges after validating names, self-edges, cycles."""
    job = get_job(conn, job_id)
    if job is None:
        raise DependencyValidationError("job not found")

    edges = normalize_dependencies(dependencies)
    seen: set[str] = set()
    for raw in dependencies:
        name = normalize_dependency(raw)["name"]
        if name in seen:
            raise DependencyValidationError(f"duplicate dependency: {name}")
        seen.add(name)
    valid_names = {
        row["name"] for row in conn.execute("SELECT name FROM jobs").fetchall()
    }
    for edge in edges:
        if edge["name"] == job["name"]:
            raise DependencyValidationError("a job cannot depend on itself")
        if edge["name"] not in valid_names:
            raise DependencyValidationError(f"unknown upstream job: {edge['name']}")

    _assert_no_cycle(conn, job_id, edges)
    conn.execute(
        "UPDATE jobs SET depends_on_json=? WHERE id=?",
        (json.dumps(edges, ensure_ascii=False), job_id),
    )
    return edges
