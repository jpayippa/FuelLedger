import json
import os
import sqlite3
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
DB_PATH = os.path.join(DATA_DIR, "gas_tracker.db")

os.makedirs(RECEIPTS_DIR, exist_ok=True)

NEW_COLUMNS = {
    "station": "TEXT",
    "volume": "REAL",
    "volume_unit": "TEXT",
    "price_per_unit": "REAL",
    "confidence_json": "TEXT",
}


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
    migrate_schema()


def migrate_schema():
    conn = get_db()
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(receipts)")}
    for column, coltype in NEW_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE receipts ADD COLUMN {column} {coltype}")
    conn.commit()
    conn.close()


def insert_receipt(date_str, amount_cents, image_filename, raw_text,
                    station=None, volume=None, volume_unit=None, price_per_unit=None,
                    confidence=None):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO receipts "
        "(date, amount_cents, image_filename, raw_ocr_text, created_at, "
        " station, volume, volume_unit, price_per_unit, confidence_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            date_str, amount_cents, image_filename, raw_text,
            datetime.now(timezone.utc).isoformat(),
            station, volume, volume_unit, price_per_unit,
            json.dumps(confidence) if confidence is not None else None,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_receipts():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, date, amount_cents, image_filename, created_at, "
        "station, volume, volume_unit, price_per_unit, confidence_json "
        "FROM receipts ORDER BY date DESC, id DESC"
    ).fetchall()
    conn.close()
    receipts = []
    for r in rows:
        d = dict(r)
        try:
            d["confidence"] = json.loads(d.pop("confidence_json")) if d.get("confidence_json") else {}
        except (TypeError, ValueError):
            d["confidence"] = {}
            d.pop("confidence_json", None)
        receipts.append(d)
    return receipts


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


# ---- Analytics ----

def get_weekly_totals(weeks=12):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT strftime('%Y-W%W', date) AS period, SUM(amount_cents) AS total_cents, COUNT(*) AS count
        FROM receipts GROUP BY period ORDER BY period DESC LIMIT ?
        """,
        (weeks,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_monthly_totals(months=12):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m', date) AS period, SUM(amount_cents) AS total_cents, COUNT(*) AS count,
               AVG(price_per_unit) AS avg_price_per_unit
        FROM receipts GROUP BY period ORDER BY period DESC LIMIT ?
        """,
        (months,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_yearly_totals():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT strftime('%Y', date) AS year, SUM(amount_cents) AS total_cents, COUNT(*) AS count
        FROM receipts GROUP BY year ORDER BY year
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_year_month_matrix(max_years=4):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT strftime('%Y', date) AS year, strftime('%m', date) AS month, SUM(amount_cents) AS total_cents
        FROM receipts GROUP BY year, month
        """
    ).fetchall()
    conn.close()
    years = sorted({r["year"] for r in rows}, reverse=True)[:max_years]
    matrix = {y: [0] * 12 for y in years}
    for r in rows:
        if r["year"] in matrix:
            matrix[r["year"]][int(r["month"]) - 1] = r["total_cents"]
    return {y: matrix[y] for y in sorted(matrix)}


def get_price_trend(limit=60):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, price_per_unit, volume_unit FROM receipts "
        "WHERE price_per_unit IS NOT NULL ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_summary_stats():
    conn = get_db()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount_cents), 0) AS total_cents,
               COUNT(*) AS count,
               COALESCE(AVG(amount_cents), 0) AS avg_cents,
               AVG(price_per_unit) AS avg_price_per_unit
        FROM receipts
        """
    ).fetchone()
    this_month = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) AS total_cents FROM receipts "
        "WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
    ).fetchone()
    conn.close()
    return {
        "total_cents": row["total_cents"],
        "count": row["count"],
        "avg_cents": row["avg_cents"],
        "avg_price_per_unit": row["avg_price_per_unit"],
        "this_month_cents": this_month["total_cents"],
    }
