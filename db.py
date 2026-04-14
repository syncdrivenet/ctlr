import sqlite3
from config import DB_PATH

def init():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            uuid TEXT PRIMARY KEY,
            started_at INTEGER,
            stopped_at INTEGER
        )
    """)
    db.commit()
    db.close()

def insert_session(uuid: str, started_at: int):
    db = sqlite3.connect(DB_PATH)
    db.execute("INSERT INTO sessions (uuid, started_at) VALUES (?, ?)", (uuid, started_at))
    db.commit()
    db.close()

def update_session_stop(uuid: str, stopped_at: int):
    db = sqlite3.connect(DB_PATH)
    db.execute("UPDATE sessions SET stopped_at = ? WHERE uuid = ?", (stopped_at, uuid))
    db.commit()
    db.close()

def get_sessions(limit: int = 50):
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT uuid, started_at, stopped_at FROM sessions ORDER BY started_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
