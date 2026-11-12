"""Dependency edges with a hard/soft kind and per-run readiness evaluation.

An edge is stored as ``{"name": "<upstream job>", "kind": "hard" | "soft"}``.
A *hard* edge must have succeeded in the current orchestration before the
downstream job may run.  A *soft* edge may be missing: the downstream job still
runs, but the attempt is marked as degraded and carries the missing-upstream
marker.  Legacy ``depends_on`` lists of plain names are treated as hard.
"""

from __future__ import annotations

from typing import Any, Iterable

VALID_DEPENDENCY_KINDS = ("hard", "soft")

# Synthetic upstream state when a dependency did not produce an attempt in the
# current orchestration (disabled job, unknown name, or not reached yet).
UPSTREAM_NOT_RUN = "not_run"
UPSTREAM_SUCCESS = "success"


def normalize_dependency(raw: Any) -> dict[str, str]:
    """Accept a legacy name or an edge object and return a canonical edge."""
    if isinstance(raw, str):
        name, kind = raw, "hard"
    elif isinstance(raw, dict):
        name = raw.get("name")
        kind = raw.get("kind", "hard")
    else:
        raise ValueError(f"dependency edge must be a name or object, got {raw!r}")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("dependency edge name is required")
    if kind not in VALID_DEPENDENCY_KINDS:
        raise ValueError(f"dependency kind must be one of {VALID_DEPENDENCY_KINDS}")
    return {"name": name.strip(), "kind": kind}


def normalize_dependencies(raw: Iterable[Any] | None) -> list[dict[str, str]]:
    """Normalize a stored ``depends_on_json`` payload, collapsing duplicates.

    If the same upstream is declared both hard and soft, hard wins because it is
    the stricter gate.
    """
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("dependencies must be a list")
    edges: list[dict[str, str]] = []
    by_name: dict[str, dict[str, str]] = {}
    for item in raw:
        edge = normalize_dependency(item)
        existing = by_name.get(edge["name"])
        if existing is not None:
            if edge["kind"] == "hard":
                existing["kind"] = "hard"
            continue
        by_name[edge["name"]] = edge
        edges.append(edge)
    return edges


def dependency_names(dependencies: Iterable[Any]) -> list[str]:
    return [edge["name"] for edge in normalize_dependencies(list(dependencies))]


def evaluate_dependencies(
    dependencies: Iterable[Any],
    upstream_states: dict[str, str],
) -> dict[str, Any]:
    """Evaluate edges against the statuses observed earlier in this run.

    Returns a structured verdict so callers can both decide whether to execute
    and record why.  ``ready`` false always means a hard edge is unsatisfied and
    the job must not execute.  ``degraded_mode`` true means all hard edges are
    satisfied but at least one soft edge is missing.
    """
    edges = normalize_dependencies(list(dependencies))
    blocking: list[dict[str, str]] = []
    degraded: list[dict[str, str]] = []

    for edge in edges:
        state = upstream_states.get(edge["name"], UPSTREAM_NOT_RUN)
        if state == UPSTREAM_SUCCESS:
            continue
        item = {
            "name": edge["name"],
            "kind": edge["kind"],
            "upstream_status": state,
        }
        if edge["kind"] == "hard":
            blocking.append(item)
        else:
            degraded.append(item)

    if blocking:
        names = ", ".join(
            f"{item['name']} ({item['upstream_status']})" for item in blocking
        )
        return {
            "ready": False,
            "hard_blocked": True,
            "degraded_mode": False,
            "blocking": blocking,
            "soft_missing": degraded,
            "reason": f"hard dependency not satisfied: {names}",
        }

    if degraded:
        names = ", ".join(
            f"{item['name']} ({item['upstream_status']})" for item in degraded
        )
        return {
            "ready": True,
            "hard_blocked": False,
            "degraded_mode": True,
            "blocking": [],
            "soft_missing": degraded,
            "reason": f"soft dependency missing, continuing degraded: {names}",
        }

    return {
        "ready": True,
        "hard_blocked": False,
        "degraded_mode": False,
        "blocking": [],
        "soft_missing": [],
        "reason": "all dependencies succeeded",
    }


def ready_by_upstream_success(
    depends_on: list[str],
    success_job_names: set[str],
) -> tuple[bool, str]:
    """Legacy helper kept for callers/tests: treat every edge as hard."""
    states = {name: UPSTREAM_SUCCESS for name in success_job_names}
    verdict = evaluate_dependencies(depends_on, states)
    return bool(verdict["ready"]), str(verdict["reason"])


def topological_layers(jobs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group jobs into layers by declared dependency names (kind-agnostic)."""
    by_name = {j["name"]: j for j in jobs}
    remaining = set(by_name)
    done: set[str] = set()
    layers: list[list[dict[str, Any]]] = []
    while remaining:
        layer = []
        for name in sorted(remaining):
            deps = dependency_names(by_name[name].get("dependencies") or by_name[name].get("depends_on", []))
            if all(d in done for d in deps):
                layer.append(by_name[name])
        if not layer:
            # cycle or missing dep — dump rest as final layer for visibility
            layers.append([by_name[n] for n in sorted(remaining)])
            break
        layers.append(layer)
        for j in layer:
            remaining.remove(j["name"])
            done.add(j["name"])
    return layers
