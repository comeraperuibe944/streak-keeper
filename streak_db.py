import sqlite3
import os
from datetime import datetime

DEFAULT_DB_PATH = "/home/ubuntu/streak-keeper/streak.db"

def get_db(db_path=DEFAULT_DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    
    # Table: commit queue
    c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            branch TEXT DEFAULT 'main',
            file_path TEXT NOT NULL,
            commit_message TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            scheduled_at TEXT,
            executed_at TEXT,
            commit_sha TEXT,
            error TEXT
        )
    """)
    
    # Table: commit history
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            commit_sha TEXT,
            commit_message TEXT NOT NULL,
            commit_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT
        )
    """)
    
    # Table: settings
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # Default settings
    default_settings = {
        "fallback_enabled": "true",
        "fallback_time": "23:15",
        "fallback_repo": "comeraperuibe944/streak-keeper",
        "check_manual_commits_first": "true",
        "author_name": "comeraperuibe944",
        "author_email": "juanperuibe6@gmail.com",
        "fallback_type": "telemetry",
        "last_fallback_date": ""
    }
    
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_settings(db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

def update_settings(updates: dict, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    for k, v in updates.items():
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()

def add_to_queue(repo, file_path, commit_message, content, branch="main", scheduled_at=None, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    created_at = datetime.now().isoformat()
    c.execute("""
        INSERT INTO queue (repo, branch, file_path, commit_message, content, status, created_at, scheduled_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
    """, (repo, branch, file_path, commit_message, content, created_at, scheduled_at))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def get_queue(status=None, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    if status:
        c.execute("SELECT * FROM queue WHERE status = ? ORDER BY id ASC", (status,))
    else:
        c.execute("SELECT * FROM queue ORDER BY id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_queue_item(item_id: int, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    c.execute("SELECT * FROM queue WHERE id = ?", (item_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_queue_item(item_id: int, status: str, commit_sha: str = None, error: str = None, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    executed_at = datetime.now().isoformat() if status in ('completed', 'failed') else None
    c.execute("""
        UPDATE queue 
        SET status = ?, commit_sha = ?, error = ?, executed_at = ?
        WHERE id = ?
    """, (status, commit_sha, error, executed_at, item_id))
    conn.commit()
    conn.close()

def delete_queue_item(item_id: int, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM queue WHERE id = ?", (item_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def record_history(repo, commit_sha, commit_message, commit_type, status, details=None, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""
        INSERT INTO history (repo, commit_sha, commit_message, commit_type, timestamp, status, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (repo, commit_sha, commit_message, commit_type, timestamp, status, details))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def get_history(limit=50, db_path=DEFAULT_DB_PATH):
    conn = get_db(db_path)
    c = conn.cursor()
    c.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
