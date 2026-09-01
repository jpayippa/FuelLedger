"""Proves db.db_conn() always closes its connection, even when the wrapped
operation raises - regression coverage for the connection-leak bug where
every db.py function used to call get_db()/conn.close() manually with no
try/finally, so a mid-function exception (e.g. a constraint violation) left
the connection open."""

import sqlite3

import pytest

import db


class _CloseSpy:
    """Wraps a real connection, recording whether close() was ever called,
    while delegating everything else (execute, commit, row_factory, ...) to
    the real connection underneath."""

    def __init__(self, real_conn):
        object.__setattr__(self, "_real", real_conn)
        object.__setattr__(self, "closed", False)

    def close(self):
        object.__setattr__(self, "closed", True)
        self._real.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture()
def spying_get_db(fresh_db, monkeypatch):
    spies = []
    real_get_db = db.get_db

    def spying():
        spy = _CloseSpy(real_get_db())
        spies.append(spy)
        return spy

    monkeypatch.setattr(db, "get_db", spying)
    return spies


def test_connection_closed_when_operation_succeeds(spying_get_db):
    db.insert_vehicle("Test Car", None, None, None, None, None)
    assert spying_get_db, "get_db was never called"
    assert spying_get_db[-1].closed


def test_connection_closed_when_operation_raises(spying_get_db):
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_fuel_log(999999, None, "2026-01-01", 1000, None, None, None, None, None, None, "", None)
    assert spying_get_db, "get_db was never called"
    assert spying_get_db[-1].closed, "connection was not closed after the operation raised"


def test_connection_closed_when_read_query_raises(spying_get_db):
    with pytest.raises(sqlite3.OperationalError):
        with db.db_conn() as conn:
            conn.execute("SELECT * FROM no_such_table")
    assert spying_get_db[-1].closed
