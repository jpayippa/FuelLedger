import io
import os
import sqlite3

from PIL import Image

import app as flask_app_module
from tests.ocr_fixtures import CLEAN_FUEL_RECEIPT, make_synthetic_receipt


def jpeg_bytes(pil_image):
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG")
    buf.seek(0)
    return buf


class TestScanRoute:
    def test_scan_rejects_non_image_upload(self, client):
        res = client.post("/scan", data={"receipt": (io.BytesIO(b"not an image"), "fake.jpg")},
                           content_type="multipart/form-data")
        assert res.status_code == 400
        assert "error" in res.get_json()

    def test_scan_accepts_real_receipt_image(self, client):
        image = make_synthetic_receipt(CLEAN_FUEL_RECEIPT)
        res = client.post("/scan", data={"receipt": (jpeg_bytes(image), "receipt.jpg")},
                           content_type="multipart/form-data")
        assert res.status_code == 200
        assert res.get_json()["amount"] == 43.75


class TestSaveFuelUploadSafety:
    def test_bad_image_rejected_with_no_orphan_row_or_file(self, client, vehicle_id, fresh_db):
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "10.00",
            "receipt": (io.BytesIO(b"not an image"), "fake.jpg"),
        }, content_type="multipart/form-data")
        assert res.status_code == 400
        assert fresh_db.list_fuel_logs(vehicle_id) == []
        assert os.listdir(fresh_db.RECEIPTS_DIR) == []

    def test_save_without_any_file_still_succeeds(self, client, vehicle_id):
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "10.00",
        })
        assert res.status_code == 200

    def test_valid_image_is_saved_and_oriented(self, client, vehicle_id, fresh_db):
        img = Image.new("RGB", (100, 50), "red")
        exif = img.getexif()
        exif[274] = 6  # needs a 90-degree correction
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        buf.seek(0)

        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "10.00",
            "receipt": (buf, "receipt.jpg"),
        }, content_type="multipart/form-data")
        assert res.status_code == 200

        logs = fresh_db.list_fuel_logs(vehicle_id)
        assert logs[0]["image_filename"] is not None
        saved_path = os.path.join(fresh_db.RECEIPTS_DIR, logs[0]["image_filename"])
        with Image.open(saved_path) as saved:
            # orientation corrected before saving: dimensions should be swapped (tall, not wide)
            assert saved.size[1] > saved.size[0]


class TestOrphanFileCleanup:
    def test_failed_insert_does_not_leave_orphaned_image(self, client, fresh_db, vehicle_id, monkeypatch):
        # A known-bad vehicle_id is now rejected before the image is ever
        # saved (see db.vehicle_exists), so it no longer exercises this
        # cleanup path. Force a failure at insert time instead, on an
        # otherwise-valid request, to prove the save_fuel() except-block
        # cleanup still works for whatever reason the insert might fail.
        def failing_insert(*args, **kwargs):
            raise sqlite3.IntegrityError("simulated failure")

        monkeypatch.setattr(flask_app_module.db, "insert_fuel_log", failing_insert)

        image = make_synthetic_receipt(CLEAN_FUEL_RECEIPT)
        res = client.post("/save/fuel", data={
            "vehicle_id": str(vehicle_id), "date": "2026-01-01", "amount": "10.00",
            "receipt": (jpeg_bytes(image), "receipt.jpg"),
        }, content_type="multipart/form-data")
        assert res.status_code == 400
        assert os.listdir(fresh_db.RECEIPTS_DIR) == []


class TestMaxContentLength:
    def test_oversized_request_returns_413(self, client, monkeypatch):
        monkeypatch.setitem(flask_app_module.app.config, "MAX_CONTENT_LENGTH", 100)
        big_payload = b"x" * 1000
        res = client.post("/save/fuel", data={
            "vehicle_id": "1", "date": "2026-01-01", "amount": "10.00",
            "receipt": (io.BytesIO(big_payload), "receipt.jpg"),
        }, content_type="multipart/form-data")
        assert res.status_code == 413
        assert "error" in res.get_json()
