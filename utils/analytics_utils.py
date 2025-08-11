# utils/analytics_utils.py
import sqlite3
from datetime import datetime
from collections import defaultdict
from typing import List, Tuple, Dict, Any
import os

DB_PATH = 'workorder.db'


# ----------------- helpers -----------------
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def query_db(query: str, args: tuple = (), one: bool = False):
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv

def fetch_scalar(query: str, args: tuple = ()):
    row = query_db(query, args, one=True)
    return row[0] if row else 0

def get_table_columns(table: str) -> List[str]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table});")
        return [r["name"] for r in cur.fetchall()]

def has_col(col: str) -> bool:
    return col in get_table_columns("tasks")

def _pick_completion_field() -> str:
    return "completed_at" if has_col("completed_at") else "deadline"

def _safe_dt(s: str | None):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass
    try:
        return datetime.fromisoformat(s)
    except:
        return None


# ----------------- what you asked for -----------------

def get_status_counts() -> Dict[str, int]:
    return {
        "pending": fetch_scalar("SELECT COUNT(*) FROM tasks WHERE status='Pending'"),
        "in_progress": fetch_scalar("SELECT COUNT(*) FROM tasks WHERE status='In Progress'"),
        "done": fetch_scalar("SELECT COUNT(*) FROM tasks WHERE status='Done'")
    }

def get_overdue_count() -> int:
    # tasks past deadline & not Done
    return fetch_scalar("""
        SELECT COUNT(*) FROM tasks
        WHERE status != 'Done'
          AND deadline IS NOT NULL
          AND datetime(deadline) < datetime('now')
    """)

def get_upcoming_count(days: int = 3) -> int:
    return fetch_scalar(f"""
        SELECT COUNT(*) FROM tasks
        WHERE status != 'Done'
          AND deadline IS NOT NULL
          AND datetime(deadline) BETWEEN datetime('now') AND datetime('now', '+{days} days')
    """)

def get_task_throughput(days: int = 7) -> List[Tuple[str, int]]:
    completion = _pick_completion_field()
    rows = query_db(f"""
        SELECT DATE({completion}) d, COUNT(*) c
        FROM tasks
        WHERE status='Done' AND {completion} IS NOT NULL
          AND DATE({completion}) >= DATE('now', ?)
        GROUP BY DATE({completion})
        ORDER BY DATE({completion})
    """, (f'-{days} days',))
    return [(r["d"], r["c"]) for r in rows]

def get_heatmap_data() -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
    area_rows = query_db("SELECT area, COUNT(*) c FROM tasks GROUP BY area ORDER BY c DESC;")
    machine_rows = query_db("SELECT machine_id, COUNT(*) c FROM tasks GROUP BY machine_id ORDER BY c DESC;")
    return (
        [((r['area'] or "Unspecified"), r['c']) for r in area_rows],
        [((r['machine_id'] or "Unspecified"), r['c']) for r in machine_rows]
    )

def get_leaderboard(limit: int = 5) -> List[Tuple[str, int, float]]:
    completion = _pick_completion_field()
    if has_col("created_at"):
        rows = query_db(f"""
            SELECT u.username AS worker_name,
                   COUNT(t.id) AS tasks_done,
                   AVG(julianday({completion}) - julianday(created_at)) AS avg_days
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE t.status='Done' AND {completion} IS NOT NULL AND created_at IS NOT NULL
            GROUP BY worker_name
            ORDER BY tasks_done DESC
            LIMIT ?;
        """, (limit,))
        return [(r["worker_name"] or "Unknown", r["tasks_done"], round(r["avg_days"] or 0, 2)) for r in rows]
    else:
        rows = query_db("""
            SELECT u.username AS worker_name,
                   COUNT(t.id) AS tasks_done
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE t.status='Done'
            GROUP BY worker_name
            ORDER BY tasks_done DESC
            LIMIT ?;
        """, (limit,))
        return [(r["worker_name"] or "Unknown", r["tasks_done"], 0.0) for r in rows]

def get_cycle_time_avg() -> float:
    if not has_col("created_at"):
        return 0.0
    completion = _pick_completion_field()
    rows = query_db(f"""
        SELECT created_at, {completion} AS done_at
        FROM tasks
        WHERE status='Done' AND created_at IS NOT NULL AND {completion} IS NOT NULL
    """)
    diffs = []
    for r in rows:
        s, e = _safe_dt(r["created_at"]), _safe_dt(r["done_at"])
        if s and e:
            diffs.append((e - s).total_seconds() / 86400.0)
    return round(sum(diffs) / len(diffs), 2) if diffs else 0.0

def get_on_time_percentage() -> float:
    completion = _pick_completion_field()
    rows = query_db(f"""
        SELECT deadline, {completion} AS done_at
        FROM tasks
        WHERE status='Done'
          AND deadline IS NOT NULL
          AND {completion} IS NOT NULL
    """)
    total = len(rows)
    if total == 0:
        return 0.0
    ok = 0
    for r in rows:
        d, c = _safe_dt(r["deadline"]), _safe_dt(r["done_at"])
        if d and c and c <= d:
            ok += 1
    return round((ok / total) * 100, 2)

def get_bottleneck_top_areas(top_n=100):
    """
    Return a list of (area, count) for areas that currently have
    Pending / In Progress tasks. Whitespace-only / NULL areas are ignored.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT TRIM(area) AS area,
               COUNT(*)   AS cnt
        FROM tasks
        WHERE status IN ('Pending', 'In Progress')
          AND TRIM(COALESCE(area, '')) <> ''
        GROUP BY TRIM(area)
        ORDER BY cnt DESC
        LIMIT ?
    """, (top_n,))

    rows = cur.fetchall()
    conn.close()

    return [(r["area"], r["cnt"]) for r in rows]
