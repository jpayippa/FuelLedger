"""Flask route tests via the test client - both success paths and failure
inputs."""

import io
import zipfile


# ---- Success paths ----

class TestPageRoutes:
    def test_index_with_no_vehicles(self, client):
        assert client.get("/").status_code == 200

    def test_index_with_a_vehicle(self, client, vehicle_id):
        assert client.get("/").status_code == 200

    def test_vehicles_page(self, client):
        assert client.get("/vehicles").status_code == 200

    def test_analytics_page(self, client):
        assert client.get("/analytics").status_code == 200

    def test_timeline_page_known_vehicle(self, client, vehicle_id):
        assert client.get(f"/timeline/{vehicle_id}").status_code == 200


class TestVehicleAndPaymentMethodApi:
    def test_create_and_list_vehicle(self, client):
        res = client.post("/api/vehicles", json={"name": "Civic", "year": 2020})
        assert res.status_code == 200
        vid = res.get_json()["id"]

        res = client.get("/api/vehicles")
        names = [v["name"] for v in res.get_json()["vehicles"]]
        assert "Civic" in names
        assert vid is not None

    def test_archive_vehicle(self, client, vehicle_id):
        res = client.post(f"/api/vehicles/{vehicle_id}/archive", json={"archived": True})
        assert res.status_code == 200

    def test_delete_vehicle_with_records_is_rejected(self, client, vehicle_id, fresh_db):
        fresh_db.insert_fuel_log(vehicle_id, None, "2026-01-01", 5000, None, None, None, None, None, None, "", None)
        res = client.post(f"/api/vehicles/{vehicle_id}/delete")
        assert res.status_code == 400
        assert "archive" in res.get_json()["error"].lower()

    def test_delete_vehicle_without_records_succeeds(self, client, vehicle_id):
        res = client.post(f"/api/vehicles/{vehicle_id}/delete")
        assert res.status_code == 200

    def test_create_and_list_payment_method(self, client):
        res = client.post("/api/payment-methods", json={"name": "Visa", "card_last4": "1234"})
        assert res.status_code == 200
        res = client.get("/api/payment-methods")
        assert any(p["name"] == "Visa" for p in res.get_json()["payment_methods"])

    def test_archive_payment_method(self, client):
        res = client.post("/api/payment-methods", json={"name": "Visa"})
        pmid = res.get_json()["id"]
        res = client.post(f"/api/payment-methods/{pmid}/archive", json={"archived": True})
        assert res.status_code == 200


class TestRecordRoutes:
    def test_save_and_list_fuel_log(self, client, vehicle_id):
        res = client.post("/save/fuel", data={"vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "31.94"})
        assert res.status_code == 200

        res = client.get(f"/api/fuel-logs?vehicle_id={vehicle_id}")
        logs = res.get_json()["logs"]
        assert len(logs) == 1
        assert logs[0]["amount"] == 31.94

    def test_save_and_list_maintenance_log(self, client, vehicle_id):
        res = client.post("/save/maintenance", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "120.00", "category": "Oil Change",
        })
        assert res.status_code == 200
        res = client.get(f"/api/maintenance-logs?vehicle_id={vehicle_id}")
        assert len(res.get_json()["logs"]) == 1

    def test_save_and_list_odometer_log(self, client, vehicle_id):
        res = client.post("/save/odometer", json={"vehicle_id": vehicle_id, "date": "2026-01-01", "odometer": 1000})
        assert res.status_code == 200
        res = client.get(f"/api/odometer-logs?vehicle_id={vehicle_id}")
        assert len(res.get_json()["logs"]) == 1

    def test_delete_fuel_log_removes_receipt_image_file(self, client, vehicle_id, fresh_db, tmp_path):
        image_path = tmp_path / "data" / "receipts" / "test.jpg"
        image_path.write_bytes(b"fake image data")
        log_id = fresh_db.insert_fuel_log(
            vehicle_id, None, "2026-01-01", 5000, None, None, None, None, None, "test.jpg", "", None,
        )
        assert image_path.exists()

        res = client.post(f"/delete/fuel/{log_id}")
        assert res.status_code == 200
        assert not image_path.exists()

    def test_delete_nonexistent_fuel_log_is_a_no_op_200(self, client):
        # documents current behavior: deleting a record that doesn't exist is
        # idempotent (no error), not that a nonexistent id was "found"
        res = client.post("/delete/fuel/999999")
        assert res.status_code == 200
        assert res.get_json() == {"ok": True}


class TestExportRoutes:
    def test_export_xlsx(self, client, vehicle_id, fresh_db):
        fresh_db.insert_fuel_log(vehicle_id, None, "2026-01-01", 5000, None, "Shell", None, None, None, None, "", None)
        res = client.get("/export.xlsx")
        assert res.status_code == 200
        with zipfile.ZipFile(io.BytesIO(res.data)) as z:
            assert "xl/workbook.xml" in z.namelist()

    def test_export_csv(self, client, vehicle_id, fresh_db):
        fresh_db.insert_fuel_log(vehicle_id, None, "2026-01-01", 5000, None, "Shell", None, None, None, None, "", None)
        res = client.get("/export.csv")
        assert res.status_code == 200
        assert b"Shell" in res.data


# ---- Failure paths ----

class TestFailureInputs:
    def test_save_fuel_with_unknown_vehicle_id_returns_400(self, client):
        res = client.post("/save/fuel", data={"vehicle_id": "999999", "date": "2026-01-01", "amount": "10.00"})
        assert res.status_code == 400
        assert "vehicle" in res.get_json()["error"].lower()

    def test_save_fuel_with_unknown_payment_method_id_returns_400(self, client, vehicle_id):
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "10.00",
            "payment_method_id": "999999",
        })
        assert res.status_code == 400
        assert "payment method" in res.get_json()["error"].lower()

    def test_save_maintenance_with_unknown_vehicle_id_returns_400(self, client):
        res = client.post("/save/maintenance", data={
            "vehicle_id": "999999", "date": "2026-01-01", "amount": "10.00",
        })
        assert res.status_code == 400
        assert "vehicle" in res.get_json()["error"].lower()

    def test_save_odometer_with_unknown_vehicle_id_returns_400(self, client):
        res = client.post("/save/odometer", json={
            "vehicle_id": 999999, "date": "2026-01-01", "odometer": 1000,
        })
        assert res.status_code == 400
        assert "vehicle" in res.get_json()["error"].lower()

    def test_duplicate_payment_method_name_returns_400(self, client):
        client.post("/api/payment-methods", json={"name": "Visa"})
        res = client.post("/api/payment-methods", json={"name": "Visa"})
        assert res.status_code == 400
        assert "already exists" in res.get_json()["error"].lower()

    def test_save_fuel_with_invalid_odometer_returns_400(self, client, vehicle_id):
        # a provided-but-invalid value must be rejected, not silently saved as null
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "10.00", "odometer": "-5",
        })
        assert res.status_code == 400

    def test_all_vehicles_archived_index_still_renders(self, client, vehicle_id):
        client.post(f"/api/vehicles/{vehicle_id}/archive", json={"archived": True})
        res = client.get("/")
        assert res.status_code == 200

    def test_missing_vehicle_id_returns_400(self, client):
        res = client.post("/save/fuel", data={"date": "2026-01-01", "amount": "10.00"})
        assert res.status_code == 400

    def test_invalid_date_returns_400(self, client, vehicle_id):
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "not-a-date", "amount": "10.00",
        })
        assert res.status_code == 400

    def test_invalid_amount_returns_400(self, client, vehicle_id):
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "abc",
        })
        assert res.status_code == 400

    def test_malformed_json_body_returns_400(self, client):
        res = client.post("/api/vehicles", data="not json", content_type="application/json")
        assert res.status_code == 400

    def test_timeline_page_unknown_vehicle_returns_404(self, client):
        assert client.get("/timeline/999999").status_code == 404

    def test_api_timeline_unknown_vehicle_returns_empty_not_error(self, client):
        # documents current behavior: no vehicle-existence check on this
        # endpoint, so an unknown id just yields empty results rather than 404
        res = client.get("/api/timeline/999999")
        assert res.status_code == 200
        assert res.get_json() == {"timeline": [], "progression": []}
