import os
import sqlite3
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
DB_PATH = os.path.join(DATA_DIR, "gas_tracker.db")

os.makedirs(RECEIPTS_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receipts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT    NOT NULL,
            amount_cents   INTEGER NOT NULL,
            image_filename TEXT,
            raw_ocr_text   TEXT,
            created_at     TEXT    NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date)")
    conn.commit()
    conn.close()


def insert_receipt(date_str, amount_cents, image_filename, raw_text):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO receipts (date, amount_cents, image_filename, raw_ocr_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (date_str, amount_cents, image_filename, raw_text, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_receipts():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, date, amount_cents, image_filename, created_at FROM receipts ORDER BY date DESC, id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_cents():
    conn = get_db()
    row = conn.execute("SELECT COALESCE(SUM(amount_cents), 0) AS total FROM receipts").fetchone()
    conn.close()
    return row["total"]


def get_receipt(receipt_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_receipt(receipt_id):
    conn = get_db()
    row = conn.execute("SELECT image_filename FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
    conn.commit()
    conn.close()
    return row["image_filename"] if row else None
