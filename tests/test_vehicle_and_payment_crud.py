def test_insert_and_list_vehicle(fresh_db):
    vid = fresh_db.insert_vehicle("Civic", 2020, "Honda", "Civic", "Gasoline", "daily driver")
    vehicles = fresh_db.list_vehicles()
    assert len(vehicles) == 1
    assert vehicles[0]["id"] == vid
    assert vehicles[0]["name"] == "Civic"
    assert vehicles[0]["is_archived"] == 0


def test_get_vehicle_returns_none_for_unknown_id(fresh_db):
    assert fresh_db.get_vehicle(9999) is None


def test_update_vehicle(fresh_db):
    vid = fresh_db.insert_vehicle("Civic", 2020, "Honda", "Civic", "Gasoline", None)
    fresh_db.update_vehicle(vid, "Civic Sport", 2021, "Honda", "Civic Si", "Gasoline", "updated")
    v = fresh_db.get_vehicle(vid)
    assert v["name"] == "Civic Sport"
    assert v["year"] == 2021
    assert v["notes"] == "updated"


def test_archived_vehicle_excluded_from_default_list(fresh_db):
    vid = fresh_db.insert_vehicle("Civic", None, None, None, None, None)
    fresh_db.set_vehicle_archived(vid, True)
    assert fresh_db.list_vehicles() == []
    assert len(fresh_db.list_vehicles(include_archived=True)) == 1


def test_vehicle_record_count_zero_for_new_vehicle(fresh_db):
    vid = fresh_db.insert_vehicle("Civic", None, None, None, None, None)
    assert fresh_db.vehicle_record_count(vid) == 0


def test_vehicle_record_count_counts_across_all_record_types(fresh_db):
    vid = fresh_db.insert_vehicle("Civic", None, None, None, None, None)
    fresh_db.insert_fuel_log(vid, None, "2026-01-01", 5000, None, None, None, None, None, None, "", None)
    fresh_db.insert_maintenance_log(vid, None, "2026-01-02", 10000, None, "Shop", "Oil Change", None, None, None)
    fresh_db.insert_odometer_log(vid, "2026-01-03", 1000, None)
    assert fresh_db.vehicle_record_count(vid) == 3


def test_delete_vehicle_with_no_records_succeeds(fresh_db):
    vid = fresh_db.insert_vehicle("Civic", None, None, None, None, None)
    fresh_db.delete_vehicle(vid)
    assert fresh_db.get_vehicle(vid) is None


def test_insert_and_list_payment_method(fresh_db):
    pmid = fresh_db.insert_payment_method("Visa", "personal card", card_last4="1234")
    methods = fresh_db.list_payment_methods()
    assert len(methods) == 1
    assert methods[0]["id"] == pmid
    assert methods[0]["card_last4"] == "1234"


def test_archived_payment_method_excluded_from_default_list(fresh_db):
    pmid = fresh_db.insert_payment_method("Visa", None)
    fresh_db.set_payment_method_archived(pmid, True)
    assert fresh_db.list_payment_methods() == []
    assert len(fresh_db.list_payment_methods(include_archived=True)) == 1


def test_find_payment_method_by_last4(fresh_db):
    pmid = fresh_db.insert_payment_method("Visa", None, card_last4="1234")
    assert fresh_db.find_payment_method_by_last4("1234") == pmid
    assert fresh_db.find_payment_method_by_last4("9999") is None


def test_find_payment_method_by_last4_ignores_archived(fresh_db):
    pmid = fresh_db.insert_payment_method("Visa", None, card_last4="1234")
    fresh_db.set_payment_method_archived(pmid, True)
    assert fresh_db.find_payment_method_by_last4("1234") is None


def test_find_cash_payment_method(fresh_db):
    fresh_db.insert_payment_method("Cash", None)
    fresh_db.insert_payment_method("Visa", None, card_last4="1234")
    pmid = fresh_db.find_cash_payment_method()
    assert pmid is not None
    assert fresh_db.get_db().execute(
        "SELECT name FROM payment_methods WHERE id = ?", (pmid,)
    ).fetchone()["name"] == "Cash"


def test_find_cash_payment_method_returns_none_when_absent(fresh_db):
    fresh_db.insert_payment_method("Visa", None, card_last4="1234")
    assert fresh_db.find_cash_payment_method() is None
