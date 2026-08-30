from datetime import datetime, timezone

from tests.conftest import raw_connect


def _create_legacy_receipts_table(conn, rows):
    """Builds the pre-vehicle `receipts` table (V1 shape) and inserts `rows`,
    each a dict of column -> value. Mirrors the shape db.LEGACY_RECEIPTS_COLUMNS
    expects to find/extend."""
    conn.execute(
        """
        CREATE TABLE receipts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT    NOT NULL,
            amount_cents   INTEGER NOT NULL,
            image_filename TEXT,
            raw_ocr_text   TEXT,
            created_at     TEXT    NOT NULL,
            station          TEXT,
            volume           REAL,
            volume_unit      TEXT,
            price_per_unit   REAL,
            confidence_json  TEXT
        )
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        conn.execute(
            "INSERT INTO receipts (date, amount_cents, image_filename, raw_ocr_text, created_at, "
            "station, volume, volume_unit, price_per_unit, confidence_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["date"], row["amount_cents"], None, "", now,
             row.get("station"), row.get("volume"), row.get("volume_unit"),
             row.get("price_per_unit"), None),
        )
    conn.commit()


def _table_names(conn):
    return {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class TestMigrationStates:
    def test_fresh_install_has_no_legacy_table_and_no_op(self, isolated_data_dir):
        isolated_data_dir.init_db()  # no receipts table exists anywhere
        conn = raw_connect(isolated_data_dir)
        tables = _table_names(conn)
        conn.close()
        assert "receipts" not in tables
        assert "receipts_v1_backup" not in tables
        assert isolated_data_dir.list_fuel_logs() == []

    def test_upgrading_already_current_schema_is_a_noop(self, isolated_data_dir):
        isolated_data_dir.init_db()
        vid = isolated_data_dir.insert_vehicle("Civic", None, None, None, None, None)
        isolated_data_dir.insert_fuel_log(
            vid, None, "2026-06-01", 5000, None, None, None, None, None, None, "", None,
        )
        # simulate an app restart on an already-up-to-date database
        isolated_data_dir.migrate_schema()
        isolated_data_dir.migrate_legacy_receipts()
        assert len(isolated_data_dir.list_fuel_logs(vid)) == 1

    def test_normal_legacy_migration_copies_rows_and_renames_table(self, isolated_data_dir):
        isolated_data_dir._create_new_schema()
        isolated_data_dir.migrate_schema()  # adds fuel_logs.legacy_receipt_id before we seed receipts
        conn = raw_connect(isolated_data_dir)
        _create_legacy_receipts_table(conn, [
            {"date": "2026-01-01", "amount_cents": 5000, "station": "Shell", "volume": 30.0,
             "volume_unit": "L", "price_per_unit": 1.5},
            {"date": "2026-02-01", "amount_cents": 6000, "station": "Esso", "volume": 32.0,
             "volume_unit": "L", "price_per_unit": 1.6},
        ])
        conn.close()

        isolated_data_dir.migrate_legacy_receipts()

        conn = raw_connect(isolated_data_dir)
        tables = _table_names(conn)
        conn.close()
        assert "receipts_v1_backup" in tables
        assert "receipts" not in tables

        logs = isolated_data_dir.list_fuel_logs()
        assert len(logs) == 2
        assert {log["amount_cents"] for log in logs} == {5000, 6000}
        assert all(log["legacy_receipt_id"] is not None for log in logs)

        vehicles = isolated_data_dir.list_vehicles()
        assert len(vehicles) == 1
        assert vehicles[0]["name"] == "My Vehicle"

    def test_repeated_migration_does_not_duplicate_rows(self, isolated_data_dir):
        isolated_data_dir._create_new_schema()
        isolated_data_dir.migrate_schema()
        conn = raw_connect(isolated_data_dir)
        _create_legacy_receipts_table(conn, [{"date": "2026-01-01", "amount_cents": 5000}])
        conn.close()

        isolated_data_dir.migrate_legacy_receipts()
        isolated_data_dir.migrate_legacy_receipts()
        isolated_data_dir.migrate_legacy_receipts()

        assert len(isolated_data_dir.list_fuel_logs()) == 1

    def test_both_receipts_and_backup_present_are_left_untouched(self, isolated_data_dir, capsys):
        isolated_data_dir._create_new_schema()
        conn = raw_connect(isolated_data_dir)
        _create_legacy_receipts_table(conn, [{"date": "2026-01-01", "amount_cents": 5000}])
        conn.execute("CREATE TABLE receipts_v1_backup (id INTEGER PRIMARY KEY, note TEXT)")
        conn.commit()
        conn.close()

        isolated_data_dir.migrate_legacy_receipts()

        conn = raw_connect(isolated_data_dir)
        tables = _table_names(conn)
        receipts_count = conn.execute("SELECT COUNT(*) AS c FROM receipts").fetchone()["c"]
        conn.close()

        assert "receipts" in tables
        assert "receipts_v1_backup" in tables
        assert receipts_count == 1  # untouched, not copied or merged
        assert isolated_data_dir.list_fuel_logs() == []  # nothing copied
        assert "skipping legacy migration" in capsys.readouterr().err
