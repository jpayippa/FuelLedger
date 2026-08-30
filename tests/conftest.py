import os
import sqlite3
import tempfile

# A throwaway default so db.py's module-level os.makedirs(RECEIPTS_DIR) side effect
# (which runs the instant `db` is first imported, below) can't touch anything real.
# Every actual test overrides this via the isolated_data_dir/fresh_db fixtures before
# doing any real work - this value is never read by a test.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="fuelledger-test-root-"))

import pytest  # noqa: E402

import app as flask_app_module  # noqa: E402
import db  # noqa: E402


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    """Points db.py's path globals at a fresh, empty temp directory. Creates no
    schema - for tests (mainly migrations) that need to construct a specific
    starting state themselves before calling into db.py."""
    data_dir = tmp_path / "data"
    receipts_dir = data_dir / "receipts"
    receipts_dir.mkdir(parents=True)
    db_path = data_dir / "gas_tracker.db"

    monkeypatch.setattr(db, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(db, "RECEIPTS_DIR", str(receipts_dir))
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    return db


@pytest.fixture()
def fresh_db(isolated_data_dir):
    """A brand-new database with the current schema already applied - the
    common case for everything except migration tests."""
    isolated_data_dir.init_db()
    return isolated_data_dir


@pytest.fixture()
def client(fresh_db):
    """Flask test client bound to the same fresh_db for this test. Route handlers
    call db.get_db() at request time, so they transparently follow whatever path
    the fresh_db fixture just monkeypatched db.DB_PATH to, even though `app` is
    only ever imported once for the whole test session."""
    flask_app_module.app.testing = True
    return flask_app_module.app.test_client()


@pytest.fixture()
def vehicle_id(fresh_db):
    """A single ready-to-use vehicle id, for tests that need a valid FK target
    but aren't themselves testing vehicle behavior."""
    return fresh_db.insert_vehicle("Test Car", 2020, "Honda", "Civic", "Gasoline", None)


def raw_connect(fresh_db_or_isolated):
    """A plain sqlite3 connection to the current fixture's DB_PATH, for tests
    that need to construct raw historical schema states (legacy `receipts`
    table, hand-crafted rows) that db.py's own functions don't expose."""
    conn = sqlite3.connect(fresh_db_or_isolated.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
