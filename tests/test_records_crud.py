"""db.py-level CRUD for the three record types. Route-level behavior (including
receipt image file cleanup on delete) is covered in test_routes.py."""


def test_insert_and_list_fuel_log(fresh_db, vehicle_id):
    log_id = fresh_db.insert_fuel_log(
        vehicle_id, None, "2026-06-01", 5510, 1000.0, "Shell", 35.0, "L", 1.575, None, "raw", {"amount": "high"},
    )
    logs = fresh_db.list_fuel_logs(vehicle_id)
    assert len(logs) == 1
    assert logs[0]["id"] == log_id
    assert logs[0]["station"] == "Shell"
    assert logs[0]["confidence"] == {"amount": "high"}


def test_list_fuel_logs_filters_by_vehicle(fresh_db):
    v1 = fresh_db.insert_vehicle("Car 1", None, None, None, None, None)
    v2 = fresh_db.insert_vehicle("Car 2", None, None, None, None, None)
    fresh_db.insert_fuel_log(v1, None, "2026-01-01", 5000, None, None, None, None, None, None, "", None)
    fresh_db.insert_fuel_log(v2, None, "2026-01-02", 6000, None, None, None, None, None, None, "", None)
    assert len(fresh_db.list_fuel_logs(v1)) == 1
    assert len(fresh_db.list_fuel_logs(v2)) == 1
    assert len(fresh_db.list_fuel_logs()) == 2


def test_delete_fuel_log_returns_image_filename(fresh_db, vehicle_id):
    log_id = fresh_db.insert_fuel_log(
        vehicle_id, None, "2026-06-01", 5510, None, None, None, None, None, "receipt.jpg", "", None,
    )
    filename = fresh_db.delete_fuel_log(log_id)
    assert filename == "receipt.jpg"
    assert fresh_db.list_fuel_logs(vehicle_id) == []


def test_delete_nonexistent_fuel_log_returns_none(fresh_db):
    assert fresh_db.delete_fuel_log(9999) is None


def test_insert_and_list_maintenance_log(fresh_db, vehicle_id):
    log_id = fresh_db.insert_maintenance_log(
        vehicle_id, None, "2026-06-15", 12000, 1200.0, "Canadian Tire", "Oil Change", None, "routine", None,
    )
    logs = fresh_db.list_maintenance_logs(vehicle_id)
    assert len(logs) == 1
    assert logs[0]["id"] == log_id
    assert logs[0]["category"] == "Oil Change"
    assert logs[0]["notes"] == "routine"


def test_maintenance_log_category_other(fresh_db, vehicle_id):
    fresh_db.insert_maintenance_log(
        vehicle_id, None, "2026-06-15", 5000, None, "Shop", "Other", "Windshield wiper fluid", None, None,
    )
    logs = fresh_db.list_maintenance_logs(vehicle_id)
    assert logs[0]["category"] == "Other"
    assert logs[0]["category_other"] == "Windshield wiper fluid"


def test_delete_maintenance_log(fresh_db, vehicle_id):
    log_id = fresh_db.insert_maintenance_log(
        vehicle_id, None, "2026-06-15", 5000, None, None, "Other", None, None, "invoice.jpg",
    )
    filename = fresh_db.delete_maintenance_log(log_id)
    assert filename == "invoice.jpg"
    assert fresh_db.list_maintenance_logs(vehicle_id) == []


def test_insert_and_list_odometer_log(fresh_db, vehicle_id):
    log_id = fresh_db.insert_odometer_log(vehicle_id, "2026-08-01", 2200.0, "road trip")
    logs = fresh_db.list_odometer_logs(vehicle_id)
    assert len(logs) == 1
    assert logs[0]["id"] == log_id
    assert logs[0]["odometer"] == 2200.0
    assert logs[0]["note"] == "road trip"


def test_delete_odometer_log(fresh_db, vehicle_id):
    log_id = fresh_db.insert_odometer_log(vehicle_id, "2026-08-01", 2200.0, None)
    fresh_db.delete_odometer_log(log_id)
    assert fresh_db.list_odometer_logs(vehicle_id) == []
