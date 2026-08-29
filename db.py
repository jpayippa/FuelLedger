import json
import os
import sqlite3
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
    "payment_methods": {},
    "fuel_logs": {},
    "maintenance_logs": {},
    "odometer_logs": {},
}


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
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
    conn.close()

    migrate_schema()
    migrate_legacy_receipts()


def migrate_schema():
    conn = get_db()
    for table, columns in TABLE_COLUMN_MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, coltype in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    conn.commit()
    conn.close()


def migrate_legacy_receipts():
    conn = get_db()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    if "receipts_v1_backup" in tables:
        conn.close()
        return
    if "receipts" not in tables:
        conn.close()
        return

    legacy_cols = {r["name"] for r in conn.execute("PRAGMA table_info(receipts)")}
    for column, coltype in LEGACY_RECEIPTS_COLUMNS.items():
        if column not in legacy_cols:
            conn.execute(f"ALTER TABLE receipts ADD COLUMN {column} {coltype}")

    fuel_log_count = conn.execute("SELECT COUNT(*) AS c FROM fuel_logs").fetchone()["c"]
    if fuel_log_count == 0:
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

        for r in conn.execute("SELECT * FROM receipts").fetchall():
            conn.execute(
                "INSERT INTO fuel_logs "
                "(vehicle_id, payment_method_id, date, amount_cents, odometer, station, "
                " volume, volume_unit, price_per_unit, image_filename, raw_ocr_text, "
                " confidence_json, created_at) "
                "VALUES (?, NULL, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                (default_vehicle_id, r["date"], r["amount_cents"], r["station"], r["volume"],
                 r["volume_unit"], r["price_per_unit"], r["image_filename"], r["raw_ocr_text"],
                 r["confidence_json"], r["created_at"]),
            )
        conn.commit()

    conn.execute("ALTER TABLE receipts RENAME TO receipts_v1_backup")
    conn.commit()
    conn.close()


# ---- Vehicles ----

def list_vehicles(include_archived=False):
    conn = get_db()
    query = "SELECT * FROM vehicles"
    if not include_archived:
        query += " WHERE is_archived = 0"
    query += " ORDER BY name"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_vehicle(vehicle_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_vehicle(name, year, make, model, fuel_type, notes):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO vehicles (name, year, make, model, fuel_type, notes, is_archived, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (name, year, make, model, fuel_type, notes, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_vehicle(vehicle_id, name, year, make, model, fuel_type, notes):
    conn = get_db()
    conn.execute(
        "UPDATE vehicles SET name=?, year=?, make=?, model=?, fuel_type=?, notes=? WHERE id=?",
        (name, year, make, model, fuel_type, notes, vehicle_id),
    )
    conn.commit()
    conn.close()


def set_vehicle_archived(vehicle_id, archived):
    conn = get_db()
    conn.execute("UPDATE vehicles SET is_archived=? WHERE id=?", (1 if archived else 0, vehicle_id))
    conn.commit()
    conn.close()


def vehicle_record_count(vehicle_id):
    conn = get_db()
    row = conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM fuel_logs WHERE vehicle_id=?) + "
        "(SELECT COUNT(*) FROM maintenance_logs WHERE vehicle_id=?) + "
        "(SELECT COUNT(*) FROM odometer_logs WHERE vehicle_id=?) AS c",
        (vehicle_id, vehicle_id, vehicle_id),
    ).fetchone()
    conn.close()
    return row["c"]


def delete_vehicle(vehicle_id):
    conn = get_db()
    conn.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
    conn.commit()
    conn.close()


# ---- Payment methods ----

def list_payment_methods(include_archived=False):
    conn = get_db()
    query = "SELECT * FROM payment_methods"
    if not include_archived:
        query += " WHERE is_archived = 0"
    query += " ORDER BY name"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_payment_method(name, notes):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO payment_methods (name, notes, is_archived, created_at) VALUES (?, ?, 0, ?)",
        (name, notes, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def set_payment_method_archived(pm_id, archived):
    conn = get_db()
    conn.execute("UPDATE payment_methods SET is_archived=? WHERE id=?", (1 if archived else 0, pm_id))
    conn.commit()
    conn.close()


# ---- Fuel logs ----

def insert_fuel_log(vehicle_id, payment_method_id, date_str, amount_cents, odometer, station,
                     volume, volume_unit, price_per_unit, image_filename, raw_text, confidence):
    conn = get_db()
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
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_fuel_logs(vehicle_id=None):
    conn = get_db()
    query = "SELECT * FROM fuel_logs"
    params = ()
    if vehicle_id:
        query += " WHERE vehicle_id = ?"
        params = (vehicle_id,)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
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
    conn = get_db()
    row = conn.execute("SELECT image_filename FROM fuel_logs WHERE id = ?", (log_id,)).fetchone()
    conn.execute("DELETE FROM fuel_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    return row["image_filename"] if row else None


# ---- Maintenance logs ----

def insert_maintenance_log(vehicle_id, payment_method_id, date_str, amount_cents, odometer,
                            shop, category, category_other, notes, image_filename):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO maintenance_logs (vehicle_id, payment_method_id, date, amount_cents, odometer, "
        "shop, category, category_other, notes, image_filename, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (vehicle_id, payment_method_id, date_str, amount_cents, odometer, shop, category,
         category_other, notes, image_filename, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_maintenance_logs(vehicle_id=None):
    conn = get_db()
    query = "SELECT * FROM maintenance_logs"
    params = ()
    if vehicle_id:
        query += " WHERE vehicle_id = ?"
        params = (vehicle_id,)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_maintenance_log(log_id):
    conn = get_db()
    row = conn.execute("SELECT image_filename FROM maintenance_logs WHERE id = ?", (log_id,)).fetchone()
    conn.execute("DELETE FROM maintenance_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    return row["image_filename"] if row else None


# ---- Odometer logs ----

def insert_odometer_log(vehicle_id, date_str, odometer, note):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO odometer_logs (vehicle_id, date, odometer, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (vehicle_id, date_str, odometer, note, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def list_odometer_logs(vehicle_id=None):
    conn = get_db()
    query = "SELECT * FROM odometer_logs"
    params = ()
    if vehicle_id:
        query += " WHERE vehicle_id = ?"
        params = (vehicle_id,)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_odometer_log(log_id):
    conn = get_db()
    conn.execute("DELETE FROM odometer_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()


# ---- Timeline ----

def get_vehicle_timeline(vehicle_id, limit=500):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM vehicle_timeline WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT ?",
        (vehicle_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_odometer_progression(vehicle_id):
    conn = get_db()
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
    conn.close()
    return [dict(r) for r in rows]


# ---- Analytics ----

def get_weekly_totals(vehicle_id=None, weeks=12):
    conn = get_db()
    where = "WHERE vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    rows = conn.execute(
        f"""
        SELECT strftime('%Y-W%W', date) AS period, SUM(amount_cents) AS total_cents, COUNT(*) AS count
        FROM fuel_logs {where} GROUP BY period ORDER BY period DESC LIMIT ?
        """,
        params + (weeks,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_monthly_totals(vehicle_id=None, months=12):
    conn = get_db()
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
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_yearly_totals(vehicle_id=None):
    conn = get_db()
    where = "WHERE vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    rows = conn.execute(
        f"""
        SELECT strftime('%Y', date) AS year, SUM(amount_cents) AS total_cents, COUNT(*) AS count
        FROM fuel_logs {where} GROUP BY year ORDER BY year
        """,
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_year_month_matrix(vehicle_id=None, max_years=4):
    conn = get_db()
    where = "WHERE vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    rows = conn.execute(
        f"""
        SELECT strftime('%Y', date) AS year, strftime('%m', date) AS month, SUM(amount_cents) AS total_cents
        FROM fuel_logs {where} GROUP BY year, month
        """,
        params,
    ).fetchall()
    conn.close()
    years = sorted({r["year"] for r in rows}, reverse=True)[:max_years]
    matrix = {y: [0] * 12 for y in years}
    for r in rows:
        if r["year"] in matrix:
            matrix[r["year"]][int(r["month"]) - 1] = r["total_cents"]
    return {y: matrix[y] for y in sorted(matrix)}


def get_price_trend(vehicle_id=None, limit=60):
    conn = get_db()
    where = "WHERE price_per_unit IS NOT NULL"
    params = ()
    if vehicle_id:
        where += " AND vehicle_id = ?"
        params = (vehicle_id,)
    rows = conn.execute(
        f"SELECT date, price_per_unit, volume_unit FROM fuel_logs {where} ORDER BY date DESC LIMIT ?",
        params + (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_maintenance_by_category(vehicle_id=None):
    conn = get_db()
    where = "WHERE vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    rows = conn.execute(
        f"""
        SELECT category, SUM(amount_cents) AS total_cents, COUNT(*) AS count
        FROM maintenance_logs {where} GROUP BY category ORDER BY total_cents DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cost_per_km(vehicle_id):
    conn = get_db()
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
    conn.close()
    if row["max_o"] is None or row["min_o"] is None or row["max_o"] <= row["min_o"]:
        return None
    distance = row["max_o"] - row["min_o"]
    return round((cost_row["total_cents"] / 100) / distance, 4)


def get_per_vehicle_summary():
    vehicles = list_vehicles(include_archived=True)
    conn = get_db()
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
    conn.close()
    return summary


def get_summary_stats(vehicle_id=None):
    conn = get_db()
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
    conn.close()
    return {
        "total_cents": row["total_cents"],
        "count": row["count"],
        "avg_cents": row["avg_cents"],
        "avg_price_per_unit": row["avg_price_per_unit"],
        "this_month_cents": this_month["total_cents"],
        "maintenance_total_cents": maint_total["c"],
        "cost_per_km": get_cost_per_km(vehicle_id) if vehicle_id else None,
    }
