#!/usr/bin/env python3
import sqlite3
import os
import argparse
from datetime import datetime

# -------------------------------
# Config
# -------------------------------
DB_DIR = "database"
DB_NAME = "workorders.db"
DB_PATH = os.path.join(DB_DIR, DB_NAME)


# -------------------------------
# Helpers
# -------------------------------
def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def drop_db_if_exists():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"🗑️  Old database removed: {DB_PATH}")


def ensure_dir():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
        print(f"📁 Created database directory: {DB_DIR}")


# -------------------------------
# Schema
# -------------------------------
def create_schema(conn: sqlite3.Connection):
    cur = conn.cursor()

    # USERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,                 -- store a hash!
            role TEXT NOT NULL CHECK(role IN ('admin', 'worker')),
            phone TEXT,
            email TEXT UNIQUE,
            profile_pic TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # TASKS  (keep everything here so analytics are easy)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            machine_id TEXT,
            area TEXT,
            deadline DATETIME,
            assigned_to INTEGER,
            status TEXT NOT NULL DEFAULT 'Pending'
                   CHECK(status IN ('Pending', 'In Progress', 'Done', 'Deleted')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL
        );
    """)

    # If you *still* want a completed_tasks table, keep it.
    # But analytics can be done directly from tasks.completed_at.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS completed_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER UNIQUE,
            title TEXT,
            description TEXT,
            machine_id TEXT,
            area TEXT,
            deadline DATETIME,
            worker_id INTEGER,
                assigned_to INTEGER,
            proof_file TEXT,
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );
    """)

    # MESSAGES / COMMENTS PER TASK
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)

    # OPTIONAL: AUDIT LOG (recommended for admin ops)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            entity_type TEXT,
            entity_id INTEGER,
            old_value TEXT,
            new_value TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
    """)

    # -------------------------------
    # Useful indexes for speed
    # -------------------------------
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_completed_at ON tasks(completed_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_area ON tasks(area);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_task_id ON messages(task_id);")

    conn.commit()


def seed_admin(conn: sqlite3.Connection):
    """
    Seed a default admin. CHANGE THE PASSWORD to a real hash in production.
    """
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin';")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("""
            INSERT INTO users (username, password, role, email)
            VALUES (?, ?, 'admin', ?);
        """, ("admin", "admin", "admin@example.com"))
        conn.commit()
        print("👤 Seeded default admin -> username: admin, password: admin (CHANGE IT!)")


# -------------------------------
# Main
# -------------------------------
def init_database(reset: bool, seed: bool):
    ensure_dir()
    if reset:
        drop_db_if_exists()

    conn = connect_db()
    create_schema(conn)

    if seed:
        seed_admin(conn)

    conn.close()
    print(f"✅ Database initialized successfully at: {DB_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize WorkOrder database.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the database.")
    parser.add_argument("--seed", action="store_true", help="Seed a default admin user.")
    args = parser.parse_args()

    init_database(reset=args.reset, seed=args.seed)
