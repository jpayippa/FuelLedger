import contextlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
DB_PATH = os.path.join(DATA_DIR, "gas_tracker.db")

os.makedirs(RECEIPTS_DIR, exist_ok=True)

MAINTENANCE_CATEGORIES = [
    "Oil Change", "Tires", "Brakes", "Battery", "Fluids & Filters",
    "Alignment / Suspension", "Transmission", "Engine Repair", "Electrical",
    "Exhaust", "Inspection / Registration", "Body / Glass", "Car Wash / Detailing",
    "Other",
]

# additive column migrations, same pattern used for the original `receipts` table
LEGACY_RECEIPTS_COLUMNS = {
    "station": "TEXT",
    "volume": "REAL",
    "volume_unit": "TEXT",
    "price_per_unit": "REAL",
    "confidence_json": "TEXT",
}
TABLE_COLUMN_MIGRATIONS = {
    "vehicles": {},
    "payment_methods": {"card_last4": "TEXT"},
    "fuel_logs": {"legacy_receipt_id": "INTEGER"},
    "maintenance_logs": {},
    "odometer_logs": {},
}


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextlib.contextmanager
def db_conn():
    """Yields a connection from get_db() and guarantees it's closed on every
    exit path, including when the wrapped code raises - get_db() itself has
    no such guarantee, and every db.py function used to call it directly with
    a manual conn.close() that a mid-function exception would skip."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    _create_new_schema()
    migrate_schema()
    migrate_legacy_receipts()


def _create_new_schema():
    with db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                year        INTEGER,
                make        TEXT,
                model       TEXT,
                fuel_type   TEXT,
                notes       TEXT,
                is_archived INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_methods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                notes       TEXT,
                is_archived INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fuel_logs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id        INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
                payment_method_id INTEGER REFERENCES payment_methods(id) ON DELETE SET NULL,
                date              TEXT    NOT NULL,
                amount_cents      INTEGER NOT NULL,
                odometer          REAL,
                station           TEXT,
                volume            REAL,
                volume_unit       TEXT,
                price_per_unit    REAL,
                image_filename    TEXT,
                raw_ocr_text      TEXT,
                confidence_json   TEXT,
                created_at        TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS maintenance_logs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id        INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
                payment_method_id INTEGER REFERENCES payment_methods(id) ON DELETE SET NULL,
                date              TEXT    NOT NULL,
                amount_cents      INTEGER NOT NULL,
                odometer          REAL,
                shop              TEXT,
                category          TEXT    NOT NULL,
                category_other    TEXT,
                notes             TEXT,
                image_filename    TEXT,
                created_at        TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS odometer_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
                date        TEXT    NOT NULL,
                odometer    REAL    NOT NULL,
                note        TEXT,
                created_at  TEXT    NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fuel_logs_vehicle_date ON fuel_logs(vehicle_id, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_logs_vehicle_date ON maintenance_logs(vehicle_id, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_odometer_logs_vehicle_date ON odometer_logs(vehicle_id, date)")

        conn.execute("DROP VIEW IF EXISTS vehicle_timeline")
        conn.execute(
            """
            CREATE VIEW vehicle_timeline AS
            SELECT 'fuel' AS record_type, id, vehicle_id, date, amount_cents, odometer,
                   station AS description, payment_method_id, created_at
            FROM fuel_logs
            UNION ALL
            SELECT 'maintenance' AS record_type, id, vehicle_id, date, amount_cents, odometer,
                   COALESCE(category_other, category) AS description, payment_method_id, created_at
            FROM maintenance_logs
            UNION ALL
            SELECT 'odometer' AS record_type, id, vehicle_id, date, NULL AS amount_cents, odometer,
                   note AS description, NULL AS payment_method_id, created_at
            FROM odometer_logs
            """
        )
        conn.commit()


def migrate_schema():
    with db_conn() as conn:
        for table, columns in TABLE_COLUMN_MIGRATIONS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, coltype in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        # Only safe to create once the column above is guaranteed to exist.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_fuel_logs_legacy_receipt_id "
            "ON fuel_logs(legacy_receipt_id) WHERE legacy_receipt_id IS NOT NULL"
        )
        conn.commit()


def migrate_legacy_receipts():
    """One-time import of the pre-vehicle `receipts` table into `fuel_logs`.

    Each imported row is tagged with `legacy_receipt_id` (the original `receipts.id`,
    a stable key) so re-running this function is safe: rows already imported are
    identified by that tag rather than inferred from whether `fuel_logs` is empty,
    which is what caused rows to go missing if `fuel_logs` ever had unrelated data
    in it before the legacy table was migrated.
    """
    with db_conn() as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        if "receipts" not in tables:
            return

        if "receipts_v1_backup" in tables:
            # Both a legacy table and a completed backup exist at once - not a state
            # normal operation produces. Don't guess at a merge; leave both alone.
            print(
                "FuelLedger: both 'receipts' and 'receipts_v1_backup' tables exist; "
                "skipping legacy migration. Inspect the database manually.",
                file=sys.stderr,
            )
            return

        legacy_cols = {r["name"] for r in conn.execute("PRAGMA table_info(receipts)")}
        for column, coltype in LEGACY_RECEIPTS_COLUMNS.items():
            if column not in legacy_cols:
                conn.execute(f"ALTER TABLE receipts ADD COLUMN {column} {coltype}")
        conn.commit()

        already_migrated_ids = {
            r["legacy_receipt_id"]
            for r in conn.execute("SELECT legacy_receipt_id FROM fuel_logs WHERE legacy_receipt_id IS NOT NULL")
        }
        pending_rows = [r for r in conn.execute("SELECT * FROM receipts").fetchall() if r["id"] not in already_migrated_ids]

        if pending_rows:
            vehicle_count = conn.execute("SELECT COUNT(*) AS c FROM vehicles").fetchone()["c"]
            now = datetime.now(timezone.utc).isoformat()
            if vehicle_count == 0:
                cur = conn.execute(
                    "INSERT INTO vehicles (name, notes, is_archived, created_at) VALUES (?, ?, 0, ?)",
                    ("My Vehicle", "Auto-created while upgrading from gas-tracker. Rename or replace me in Vehicles.", now),
                )
                default_vehicle_id = cur.lastrowid
            else:
                default_vehicle_id = conn.execute("SELECT id FROM vehicles ORDER BY id LIMIT 1").fetchone()["id"]

            for r in pending_rows:
                conn.execute(
                    "INSERT INTO fuel_logs "
                    "(vehicle_id, payment_method_id, date, amount_cents, odometer, station, "
                    " volume, volume_unit, price_per_unit, image_filename, raw_ocr_text, "
                    " confidence_json, legacy_receipt_id, created_at) "
                    "VALUES (?, NULL, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (default_vehicle_id, r["date"], r["amount_cents"], r["station"], r["volume"],
                     r["volume_unit"], r["price_per_unit"], r["image_filename"], r["raw_ocr_text"],
                     r["confidence_json"], r["id"], r["created_at"]),
                )
            conn.commit()

        remaining = conn.execute(
            "SELECT COUNT(*) AS c FROM receipts WHERE id NOT IN "
            "(SELECT legacy_receipt_id FROM fuel_logs WHERE legacy_receipt_id IS NOT NULL)"
        ).fetchone()["c"]
        if remaining == 0:
            conn.execute("ALTER TABLE receipts RENAME TO receipts_v1_backup")
            conn.commit()


# ---- Vehicles ----

def list_vehicles(include_archived=False):
    with db_conn() as conn:
        query = "SELECT * FROM vehicles"
        if not include_archived:
            query += " WHERE is_archived = 0"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


def get_vehicle(vehicle_id):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        return dict(row) if row else None


def vehicle_exists(vehicle_id):
    with db_conn() as conn:
        row = conn.execute("SELECT 1 FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        return row is not None


def insert_vehicle(name, year, make, model, fuel_type, notes):
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO vehicles (name, year, make, model, fuel_type, notes, is_archived, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (name, year, make, model, fuel_type, notes, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def update_vehicle(vehicle_id, name, year, make, model, fuel_type, notes):
    with db_conn() as conn:
        conn.execute(
            "UPDATE vehicles SET name=?, year=?, make=?, model=?, fuel_type=?, notes=? WHERE id=?",
            (name, year, make, model, fuel_type, notes, vehicle_id),
        )
        conn.commit()


def set_vehicle_archived(vehicle_id, archived):
    with db_conn() as conn:
        conn.execute("UPDATE vehicles SET is_archived=? WHERE id=?", (1 if archived else 0, vehicle_id))
        conn.commit()


def vehicle_record_count(vehicle_id):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM fuel_logs WHERE vehicle_id=?) + "
            "(SELECT COUNT(*) FROM maintenance_logs WHERE vehicle_id=?) + "
            "(SELECT COUNT(*) FROM odometer_logs WHERE vehicle_id=?) AS c",
            (vehicle_id, vehicle_id, vehicle_id),
        ).fetchone()
        return row["c"]


def delete_vehicle(vehicle_id):
    with db_conn() as conn:
        conn.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
        conn.commit()


# ---- Payment methods ----

def list_payment_methods(include_archived=False):
    with db_conn() as conn:
        query = "SELECT * FROM payment_methods"
        if not include_archived:
            query += " WHERE is_archived = 0"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


def payment_method_exists(pm_id):
    with db_conn() as conn:
        row = conn.execute("SELECT 1 FROM payment_methods WHERE id = ?", (pm_id,)).fetchone()
        return row is not None


def payment_method_name_taken(name):
    with db_conn() as conn:
        row = conn.execute("SELECT 1 FROM payment_methods WHERE name = ?", (name,)).fetchone()
        return row is not None


def insert_payment_method(name, notes, card_last4=None):
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO payment_methods (name, notes, card_last4, is_archived, created_at) VALUES (?, ?, ?, 0, ?)",
            (name, notes, card_last4, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def set_payment_method_archived(pm_id, archived):
    with db_conn() as conn:
        conn.execute("UPDATE payment_methods SET is_archived=? WHERE id=?", (1 if archived else 0, pm_id))
        conn.commit()


def find_payment_method_by_last4(last4):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT id FROM payment_methods WHERE card_last4 = ? AND is_archived = 0 LIMIT 1", (last4,)
        ).fetchone()
        return row["id"] if row else None


def find_cash_payment_method():
    with db_conn() as conn:
        row = conn.execute(
            "SELECT id FROM payment_methods WHERE is_archived = 0 AND LOWER(name) LIKE '%cash%' LIMIT 1"
        ).fetchone()
        return row["id"] if row else None


# ---- Fuel logs ----

def insert_fuel_log(vehicle_id, payment_method_id, date_str, amount_cents, odometer, station,
                     volume, volume_unit, price_per_unit, image_filename, raw_text, confidence):
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO fuel_logs (vehicle_id, payment_method_id, date, amount_cents, odometer, "
            "station, volume, volume_unit, price_per_unit, image_filename, raw_ocr_text, "
            "confidence_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vehicle_id, payment_method_id, date_str, amount_cents, odometer, station, volume,
             volume_unit, price_per_unit, image_filename,
             raw_text, json.dumps(confidence) if confidence is not None else None,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def list_fuel_logs(vehicle_id=None):
    with db_conn() as conn:
        query = "SELECT * FROM fuel_logs"
        params = ()
        if vehicle_id:
            query += " WHERE vehicle_id = ?"
            params = (vehicle_id,)
        query += " ORDER BY date DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["confidence"] = json.loads(d.pop("confidence_json")) if d.get("confidence_json") else {}
            except (TypeError, ValueError):
                d["confidence"] = {}
                d.pop("confidence_json", None)
            result.append(d)
        return result


def delete_fuel_log(log_id):
    with db_conn() as conn:
        row = conn.execute("SELECT image_filename FROM fuel_logs WHERE id = ?", (log_id,)).fetchone()
        conn.execute("DELETE FROM fuel_logs WHERE id = ?", (log_id,))
        conn.commit()
        return row["image_filename"] if row else None


# ---- Maintenance logs ----

def insert_maintenance_log(vehicle_id, payment_method_id, date_str, amount_cents, odometer,
                            shop, category, category_other, notes, image_filename):
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO maintenance_logs (vehicle_id, payment_method_id, date, amount_cents, odometer, "
            "shop, category, category_other, notes, image_filename, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vehicle_id, payment_method_id, date_str, amount_cents, odometer, shop, category,
             category_other, notes, image_filename, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def list_maintenance_logs(vehicle_id=None):
    with db_conn() as conn:
        query = "SELECT * FROM maintenance_logs"
        params = ()
        if vehicle_id:
            query += " WHERE vehicle_id = ?"
            params = (vehicle_id,)
        query += " ORDER BY date DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_maintenance_log(log_id):
    with db_conn() as conn:
        row = conn.execute("SELECT image_filename FROM maintenance_logs WHERE id = ?", (log_id,)).fetchone()
        conn.execute("DELETE FROM maintenance_logs WHERE id = ?", (log_id,))
        conn.commit()
        return row["image_filename"] if row else None


# ---- Odometer logs ----

def insert_odometer_log(vehicle_id, date_str, odometer, note):
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO odometer_logs (vehicle_id, date, odometer, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (vehicle_id, date_str, odometer, note, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def list_odometer_logs(vehicle_id=None):
    with db_conn() as conn:
        query = "SELECT * FROM odometer_logs"
        params = ()
        if vehicle_id:
            query += " WHERE vehicle_id = ?"
            params = (vehicle_id,)
        query += " ORDER BY date DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_odometer_log(log_id):
    with db_conn() as conn:
        conn.execute("DELETE FROM odometer_logs WHERE id = ?", (log_id,))
        conn.commit()


# ---- Timeline ----

def get_vehicle_timeline(vehicle_id, limit=500):
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vehicle_timeline WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (vehicle_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_odometer_progression(vehicle_id):
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT date, odometer,
                   odometer - LAG(odometer) OVER (ORDER BY date, odometer) AS distance_since_prev
            FROM vehicle_timeline
            WHERE vehicle_id = ? AND odometer IS NOT NULL
            ORDER BY date, odometer
            """,
            (vehicle_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---- Analytics ----

def get_weekly_totals(vehicle_id=None, weeks=12):
    with db_conn() as conn:
        where = "WHERE vehicle_id = ?" if vehicle_id else ""
        params = (vehicle_id,) if vehicle_id else ()
        rows = conn.execute(
            f"""
            SELECT strftime('%Y-W%W', date) AS period, SUM(amount_cents) AS total_cents, COUNT(*) AS count
            FROM fuel_logs {where} GROUP BY period ORDER BY period DESC LIMIT ?
            """,
            params + (weeks,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_monthly_totals(vehicle_id=None, months=12):
    with db_conn() as conn:
        where = "WHERE vehicle_id = ?" if vehicle_id else ""
        params = (vehicle_id,) if vehicle_id else ()
        rows = conn.execute(
            f"""
            SELECT strftime('%Y-%m', date) AS period, SUM(amount_cents) AS total_cents, COUNT(*) AS count,
                   AVG(price_per_unit) AS avg_price_per_unit
            FROM fuel_logs {where} GROUP BY period ORDER BY period DESC LIMIT ?
            """,
            params + (months,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_yearly_totals(vehicle_id=None):
    with db_conn() as conn:
        where = "WHERE vehicle_id = ?" if vehicle_id else ""
        params = (vehicle_id,) if vehicle_id else ()
        rows = conn.execute(
            f"""
            SELECT strftime('%Y', date) AS year, SUM(amount_cents) AS total_cents, COUNT(*) AS count
            FROM fuel_logs {where} GROUP BY year ORDER BY year
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_year_month_matrix(vehicle_id=None, max_years=4):
    with db_conn() as conn:
        where = "WHERE vehicle_id = ?" if vehicle_id else ""
        params = (vehicle_id,) if vehicle_id else ()
        rows = conn.execute(
            f"""
            SELECT strftime('%Y', date) AS year, strftime('%m', date) AS month, SUM(amount_cents) AS total_cents
            FROM fuel_logs {where} GROUP BY year, month
            """,
            params,
        ).fetchall()
        years = sorted({r["year"] for r in rows}, reverse=True)[:max_years]
        matrix = {y: [0] * 12 for y in years}
        for r in rows:
            if r["year"] in matrix:
                matrix[r["year"]][int(r["month"]) - 1] = r["total_cents"]
        return {y: matrix[y] for y in sorted(matrix)}


def get_price_trend(vehicle_id=None, limit=60):
    with db_conn() as conn:
        where = "WHERE price_per_unit IS NOT NULL"
        params = ()
        if vehicle_id:
            where += " AND vehicle_id = ?"
            params = (vehicle_id,)
        rows = conn.execute(
            f"SELECT date, price_per_unit, volume_unit FROM fuel_logs {where} ORDER BY date DESC LIMIT ?",
            params + (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_maintenance_by_category(vehicle_id=None):
    with db_conn() as conn:
        where = "WHERE vehicle_id = ?" if vehicle_id else ""
        params = (vehicle_id,) if vehicle_id else ()
        rows = conn.execute(
            f"""
            SELECT category, SUM(amount_cents) AS total_cents, COUNT(*) AS count
            FROM maintenance_logs {where} GROUP BY category ORDER BY total_cents DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_cost_per_km(vehicle_id):
    with db_conn() as conn:
        row = conn.execute(
            "SELECT MAX(odometer) AS max_o, MIN(odometer) AS min_o FROM vehicle_timeline "
            "WHERE vehicle_id = ? AND odometer IS NOT NULL",
            (vehicle_id,),
        ).fetchone()
        cost_row = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total_cents FROM vehicle_timeline "
            "WHERE vehicle_id = ? AND record_type IN ('fuel', 'maintenance')",
            (vehicle_id,),
        ).fetchone()
        if row["max_o"] is None or row["min_o"] is None or row["max_o"] <= row["min_o"]:
            return None
        distance = row["max_o"] - row["min_o"]
        return round((cost_row["total_cents"] / 100) / distance, 4)


def get_per_vehicle_summary():
    vehicles = list_vehicles(include_archived=True)
    with db_conn() as conn:
        summary = []
        for v in vehicles:
            fuel = conn.execute(
                "SELECT COALESCE(SUM(amount_cents),0) AS c, COUNT(*) AS n, AVG(amount_cents) AS avg_c "
                "FROM fuel_logs WHERE vehicle_id=?", (v["id"],)
            ).fetchone()
            maint = conn.execute(
                "SELECT COALESCE(SUM(amount_cents),0) AS c, COUNT(*) AS n "
                "FROM maintenance_logs WHERE vehicle_id=?", (v["id"],)
            ).fetchone()
            summary.append({
                "vehicle": v["name"],
                "fuel_total_cents": fuel["c"],
                "fuel_count": fuel["n"],
                "avg_fill_cents": fuel["avg_c"] or 0,
                "maintenance_total_cents": maint["c"],
                "maintenance_count": maint["n"],
                "combined_total_cents": fuel["c"] + maint["c"],
                "cost_per_km": get_cost_per_km(v["id"]),
            })
        return summary


def get_summary_stats(vehicle_id=None):
    with db_conn() as conn:
        where = "WHERE vehicle_id = ?" if vehicle_id else ""
        params = (vehicle_id,) if vehicle_id else ()
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(amount_cents), 0) AS total_cents,
                   COUNT(*) AS count,
                   COALESCE(AVG(amount_cents), 0) AS avg_cents,
                   AVG(price_per_unit) AS avg_price_per_unit
            FROM fuel_logs {where}
            """,
            params,
        ).fetchone()
        month_where = where + (" AND " if where else "WHERE ") + "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
        this_month = conn.execute(
            f"SELECT COALESCE(SUM(amount_cents), 0) AS total_cents FROM fuel_logs {month_where}",
            params,
        ).fetchone()
        maint_total = conn.execute(
            f"SELECT COALESCE(SUM(amount_cents), 0) AS c FROM maintenance_logs {where}", params
        ).fetchone()
        return {
            "total_cents": row["total_cents"],
            "count": row["count"],
            "avg_cents": row["avg_cents"],
            "avg_price_per_unit": row["avg_price_per_unit"],
            "this_month_cents": this_month["total_cents"],
            "maintenance_total_cents": maint_total["c"],
            "cost_per_km": get_cost_per_km(vehicle_id) if vehicle_id else None,
        }
