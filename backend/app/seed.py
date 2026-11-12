import json

from app.db import connect


def _seed_jobs() -> list[tuple]:
    return [
        (
            "ingest_orders",
            "ingest_orders.json",
            "[]",
            1,
            1,
            "无依赖：写出订单水位",
        ),
        (
            "dim_customer",
            "dim_customer.json",
            "[]",
            1,
            1,
            "无依赖：写出客户维表水位",
        ),
        (
            "fact_order_daily",
            "fact_order_daily.json",
            json.dumps(
                [
                    {"name": "ingest_orders", "kind": "hard"},
                    {"name": "dim_customer", "kind": "hard"},
                ]
            ),
            1,
            1,
            "硬依赖两路上游成功后才执行",
        ),
    ]


def _migrate_depends_on_json(conn) -> None:
    """Upgrade legacy plain-name dependency lists to typed edges."""
    for row in conn.execute("SELECT id, depends_on_json FROM jobs").fetchall():
        raw = row["depends_on_json"] or "[]"
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = []
        if not isinstance(payload, list):
            payload = []
        edges = []
        for item in payload:
            if isinstance(item, str):
                edges.append({"name": item, "kind": "hard"})
            elif isinstance(item, dict) and item.get("name"):
                kind = item.get("kind") if item.get("kind") in ("hard", "soft") else "hard"
                edges.append({"name": item["name"], "kind": kind})
        encoded = json.dumps(edges, ensure_ascii=False)
        if encoded != raw:
            conn.execute(
                "UPDATE jobs SET depends_on_json=? WHERE id=?",
                (encoded, row["id"]),
            )


def init_db():
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            fixture_path TEXT NOT NULL,
            depends_on_json TEXT NOT NULL,
            max_attempts INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS orchestrations(
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            report_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS job_attempts(
            id INTEGER PRIMARY KEY,
            orchestration_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watermarks(
            job_id INTEGER PRIMARY KEY,
            watermark_ts TEXT,
            artifact_rows INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        """
    )
    if conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 0:
        conn.executemany(
            """
            INSERT INTO jobs(name, fixture_path, depends_on_json, max_attempts, enabled, note)
            VALUES (?,?,?,?,?,?)
            """,
            _seed_jobs(),
        )
        for row in conn.execute("SELECT id FROM jobs").fetchall():
            conn.execute(
                "INSERT OR IGNORE INTO watermarks(job_id, watermark_ts, artifact_rows, updated_at) VALUES (?,?,?,?)",
                (row["id"], None, 0, None),
            )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            ("default_max_attempts", "1"),
        )
    _migrate_depends_on_json(conn)
    conn.commit()
    conn.close()
