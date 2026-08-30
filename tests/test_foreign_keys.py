"""Confirms PRAGMA foreign_keys=ON (set in db.get_db()) actually enforces the
declared constraints at the SQLite layer, not just via application-level checks."""

import sqlite3

import pytest


def test_cannot_delete_vehicle_with_fuel_log(fresh_db, vehicle_id):
    fresh_db.insert_fuel_log(vehicle_id, None, "2026-01-01", 5000, None, None, None, None, None, None, "", None)
    conn = fresh_db.get_db()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
        conn.commit()
    conn.close()


def test_cannot_insert_fuel_log_for_unknown_vehicle(fresh_db):
    conn = fresh_db.get_db()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fuel_logs (vehicle_id, date, amount_cents, created_at) VALUES (?, ?, ?, ?)",
            (999999, "2026-01-01", 5000, "2026-01-01T00:00:00"),
        )
        conn.commit()
    conn.close()


def test_deleting_payment_method_sets_null_on_existing_records(fresh_db, vehicle_id):
    # The app itself exposes no delete route for payment methods (only archive) -
    # this exercises the ON DELETE SET NULL constraint directly at the DB layer.
    pmid = fresh_db.insert_payment_method("Visa", None, card_last4="1234")
    log_id = fresh_db.insert_fuel_log(
        vehicle_id, pmid, "2026-01-01", 5000, None, None, None, None, None, None, "", None,
    )

    conn = fresh_db.get_db()
    conn.execute("DELETE FROM payment_methods WHERE id=?", (pmid,))
    conn.commit()
    conn.close()

    logs = fresh_db.list_fuel_logs(vehicle_id)
    assert logs[0]["id"] == log_id
    assert logs[0]["payment_method_id"] is None


def test_deleting_vehicle_with_no_records_succeeds(fresh_db):
    vid = fresh_db.insert_vehicle("Unused Car", None, None, None, None, None)
    conn = fresh_db.get_db()
    conn.execute("DELETE FROM vehicles WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    assert fresh_db.get_vehicle(vid) is None
