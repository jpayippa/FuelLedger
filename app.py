import json
import os
import uuid
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from PIL import Image

import db
import ocr
import uploads
from export import build_csv, build_workbook
from uploads import ImageValidationError

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = uploads.MAX_UPLOAD_BYTES
db.init_db()


@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.errorhandler(413)
def handle_upload_too_large(e):
    return jsonify({"error": f"File too large. Maximum upload size is {uploads.MAX_UPLOAD_MB} MB."}), 413


def cents_from_amount(amount_str, max_amount=999.99):
    amount = float(amount_str)
    if not (0 < amount <= max_amount):
        raise ValueError("amount out of range")
    return round(amount * 100)


def validate_date(date_str):
    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
    if parsed > date.today():
        raise ValueError("date in the future")
    return date_str


def optional_float(value, min_val=0, max_val=1e6):
    if value in (None, ""):
        return None
    parsed = float(value)
    if not (min_val <= parsed <= max_val):
        return None
    return parsed


def optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def save_uploaded_image(file):
    """Returns the saved filename, or None if no file was provided.
    Raises ImageValidationError (never silently swallowed) if a file WAS
    provided but failed validation."""
    image = uploads.load_validated_image(file)
    if image is None:
        return None
    image = image.convert("RGB")
    image.thumbnail((2000, 2000), Image.LANCZOS)
    filename = f"{uuid.uuid4()}.jpg"
    image.save(os.path.join(db.RECEIPTS_DIR, filename), "JPEG", quality=85)
    return filename


def fuel_logs_with_dollars(vehicle_id=None):
    logs = db.list_fuel_logs(vehicle_id)
    for r in logs:
        r["amount"] = round(r["amount_cents"] / 100, 2)
    return logs


def maintenance_logs_with_dollars(vehicle_id=None):
    logs = db.list_maintenance_logs(vehicle_id)
    for r in logs:
        r["amount"] = round(r["amount_cents"] / 100, 2)
    return logs


# ---- Pages ----

@app.route("/")
def index():
    vehicles = db.list_vehicles()
    return render_template(
        "index.html",
        vehicles=vehicles,
        today=date.today().isoformat(),
        maintenance_categories=db.MAINTENANCE_CATEGORIES,
    )


@app.route("/vehicles")
def vehicles_page():
    return render_template(
        "vehicles.html",
        vehicles=db.list_vehicles(include_archived=True),
        payment_methods=db.list_payment_methods(include_archived=True),
    )


@app.route("/timeline/<int:vehicle_id>")
def timeline_page(vehicle_id):
    vehicle = db.get_vehicle(vehicle_id)
    if not vehicle:
        return "Vehicle not found", 404
    return render_template("timeline.html", vehicle=vehicle)


@app.route("/analytics")
def analytics():
    return render_template("analytics.html", vehicles=db.list_vehicles())


# ---- Vehicles API ----

@app.route("/api/vehicles", methods=["GET", "POST"])
def api_vehicles():
    if request.method == "POST":
        data = request.get_json(force=True)
        vehicle_id = db.insert_vehicle(
            data.get("name", "").strip() or "Unnamed Vehicle",
            optional_int(data.get("year")),
            (data.get("make") or "").strip() or None,
            (data.get("model") or "").strip() or None,
            (data.get("fuel_type") or "").strip() or None,
            (data.get("notes") or "").strip() or None,
        )
        return jsonify({"id": vehicle_id})
    return jsonify({"vehicles": db.list_vehicles(include_archived=True)})


@app.route("/api/vehicles/<int:vehicle_id>", methods=["POST"])
def api_update_vehicle(vehicle_id):
    data = request.get_json(force=True)
    db.update_vehicle(
        vehicle_id,
        data.get("name", "").strip() or "Unnamed Vehicle",
        optional_int(data.get("year")),
        (data.get("make") or "").strip() or None,
        (data.get("model") or "").strip() or None,
        (data.get("fuel_type") or "").strip() or None,
        (data.get("notes") or "").strip() or None,
    )
    return jsonify({"ok": True})


@app.route("/api/vehicles/<int:vehicle_id>/archive", methods=["POST"])
def api_archive_vehicle(vehicle_id):
    archived = request.get_json(force=True).get("archived", True)
    db.set_vehicle_archived(vehicle_id, archived)
    return jsonify({"ok": True})


@app.route("/api/vehicles/<int:vehicle_id>/delete", methods=["POST"])
def api_delete_vehicle(vehicle_id):
    if db.vehicle_record_count(vehicle_id) > 0:
        return jsonify({"error": "Vehicle has existing records; archive it instead of deleting."}), 400
    db.delete_vehicle(vehicle_id)
    return jsonify({"ok": True})


# ---- Payment methods API ----

@app.route("/api/payment-methods", methods=["GET", "POST"])
def api_payment_methods():
    if request.method == "POST":
        data = request.get_json(force=True)
        card_last4 = (data.get("card_last4") or "").strip() or None
        if card_last4 and (not card_last4.isdigit() or len(card_last4) != 4):
            card_last4 = None
        pm_id = db.insert_payment_method(
            data.get("name", "").strip() or "Unnamed",
            (data.get("notes") or "").strip() or None,
            card_last4=card_last4,
        )
        return jsonify({"id": pm_id})
    return jsonify({"payment_methods": db.list_payment_methods(include_archived=True)})


@app.route("/api/payment-methods/<int:pm_id>/archive", methods=["POST"])
def api_archive_payment_method(pm_id):
    archived = request.get_json(force=True).get("archived", True)
    db.set_payment_method_archived(pm_id, archived)
    return jsonify({"ok": True})


# ---- OCR ----

@app.route("/scan", methods=["POST"])
def scan():
    file = request.files.get("receipt")
    if not file:
        return jsonify({"error": "no file uploaded"}), 400
    try:
        image = uploads.load_validated_image(file)
    except ImageValidationError as e:
        return jsonify({"error": str(e)}), 400

    try:
        result = ocr.parse_receipt(image)
    except ocr.OcrBusyError as e:
        return jsonify({"error": str(e)}), 503

    payment_hint = result["payment_hint"]
    matched_payment_method_id = None
    if payment_hint["method"] == "card" and payment_hint["card_last4"]:
        matched_payment_method_id = db.find_payment_method_by_last4(payment_hint["card_last4"])
    elif payment_hint["method"] == "cash":
        matched_payment_method_id = db.find_cash_payment_method()

    return jsonify({
        "amount": result["amount"],
        "date": result["date"].isoformat() if result["date"] else None,
        "station": result["station"],
        "volume": result["volume"],
        "volume_unit": result["volume_unit"],
        "price_per_unit": result["price_per_unit"],
        "raw_text": result["raw_text"],
        "confidence": result["confidence"],
        "quality_warnings": result.get("quality_warnings", []),
        "payment_hint": payment_hint,
        "matched_payment_method_id": matched_payment_method_id,
    })


# ---- Fuel ----

@app.route("/save/fuel", methods=["POST"])
def save_fuel():
    file = request.files.get("receipt")
    date_str = request.form.get("date", "")
    amount_str = request.form.get("amount", "")
    vehicle_id = optional_int(request.form.get("vehicle_id"))
    if not vehicle_id:
        return jsonify({"error": "vehicle_id is required"}), 400

    try:
        validate_date(date_str)
        amount_cents = cents_from_amount(amount_str)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid date or amount"}), 400

    try:
        confidence = json.loads(request.form.get("confidence") or "null")
    except ValueError:
        confidence = None

    try:
        image_filename = save_uploaded_image(file)
    except ImageValidationError as e:
        return jsonify({"error": str(e)}), 400

    try:
        new_id = db.insert_fuel_log(
            vehicle_id=vehicle_id,
            payment_method_id=optional_int(request.form.get("payment_method_id")),
            date_str=date_str,
            amount_cents=amount_cents,
            odometer=optional_float(request.form.get("odometer"), max_val=2_000_000),
            station=request.form.get("station") or None,
            volume=optional_float(request.form.get("volume"), max_val=500),
            volume_unit=request.form.get("volume_unit") if request.form.get("volume_unit") in ("L", "gal") else None,
            price_per_unit=optional_float(request.form.get("price_per_unit"), max_val=10),
            image_filename=image_filename,
            raw_text=request.form.get("raw_text", ""),
            confidence=confidence,
        )
    except Exception:
        if image_filename:
            path = os.path.join(db.RECEIPTS_DIR, image_filename)
            if os.path.exists(path):
                os.remove(path)
        raise
    return jsonify({"id": new_id})


@app.route("/api/fuel-logs")
def api_fuel_logs():
    vehicle_id = optional_int(request.args.get("vehicle_id"))
    return jsonify({"logs": fuel_logs_with_dollars(vehicle_id)})


@app.route("/delete/fuel/<int:log_id>", methods=["POST"])
def delete_fuel(log_id):
    image_filename = db.delete_fuel_log(log_id)
    if image_filename:
        path = os.path.join(db.RECEIPTS_DIR, image_filename)
        if os.path.exists(path):
            os.remove(path)
    return jsonify({"ok": True})


# ---- Maintenance ----

@app.route("/save/maintenance", methods=["POST"])
def save_maintenance():
    file = request.files.get("receipt")
    date_str = request.form.get("date", "")
    amount_str = request.form.get("amount", "")
    vehicle_id = optional_int(request.form.get("vehicle_id"))
    category = request.form.get("category") or "Other"
    if not vehicle_id:
        return jsonify({"error": "vehicle_id is required"}), 400
    if category not in db.MAINTENANCE_CATEGORIES:
        category = "Other"

    try:
        validate_date(date_str)
        amount_cents = cents_from_amount(amount_str, max_amount=99999.99)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid date or amount"}), 400

    try:
        image_filename = save_uploaded_image(file)
    except ImageValidationError as e:
        return jsonify({"error": str(e)}), 400

    try:
        new_id = db.insert_maintenance_log(
            vehicle_id=vehicle_id,
            payment_method_id=optional_int(request.form.get("payment_method_id")),
            date_str=date_str,
            amount_cents=amount_cents,
            odometer=optional_float(request.form.get("odometer"), max_val=2_000_000),
            shop=request.form.get("shop") or None,
            category=category,
            category_other=(request.form.get("category_other") or None) if category == "Other" else None,
            notes=request.form.get("notes") or None,
            image_filename=image_filename,
        )
    except Exception:
        if image_filename:
            path = os.path.join(db.RECEIPTS_DIR, image_filename)
            if os.path.exists(path):
                os.remove(path)
        raise
    return jsonify({"id": new_id})


@app.route("/api/maintenance-logs")
def api_maintenance_logs():
    vehicle_id = optional_int(request.args.get("vehicle_id"))
    return jsonify({"logs": maintenance_logs_with_dollars(vehicle_id)})


@app.route("/delete/maintenance/<int:log_id>", methods=["POST"])
def delete_maintenance(log_id):
    image_filename = db.delete_maintenance_log(log_id)
    if image_filename:
        path = os.path.join(db.RECEIPTS_DIR, image_filename)
        if os.path.exists(path):
            os.remove(path)
    return jsonify({"ok": True})


# ---- Odometer ----

@app.route("/save/odometer", methods=["POST"])
def save_odometer():
    data = request.get_json(force=True)
    vehicle_id = optional_int(data.get("vehicle_id"))
    date_str = data.get("date", "")
    if not vehicle_id:
        return jsonify({"error": "vehicle_id is required"}), 400
    try:
        validate_date(date_str)
        odometer = float(data.get("odometer"))
        if not (0 <= odometer <= 2_000_000):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "invalid date or odometer"}), 400

    new_id = db.insert_odometer_log(vehicle_id, date_str, odometer, (data.get("note") or None))
    return jsonify({"id": new_id})


@app.route("/api/odometer-logs")
def api_odometer_logs():
    vehicle_id = optional_int(request.args.get("vehicle_id"))
    return jsonify({"logs": db.list_odometer_logs(vehicle_id)})


@app.route("/delete/odometer/<int:log_id>", methods=["POST"])
def delete_odometer(log_id):
    db.delete_odometer_log(log_id)
    return jsonify({"ok": True})


# ---- Timeline ----

@app.route("/api/timeline/<int:vehicle_id>")
def api_timeline(vehicle_id):
    return jsonify({
        "timeline": db.get_vehicle_timeline(vehicle_id),
        "progression": db.get_odometer_progression(vehicle_id),
    })


# ---- Analytics ----

@app.route("/api/analytics")
def api_analytics():
    vehicle_id = optional_int(request.args.get("vehicle_id"))
    stats = db.get_summary_stats(vehicle_id)
    return jsonify({
        "weekly": db.get_weekly_totals(vehicle_id),
        "monthly": db.get_monthly_totals(vehicle_id),
        "yearly": db.get_yearly_totals(vehicle_id),
        "year_month_matrix": db.get_year_month_matrix(vehicle_id),
        "price_trend": db.get_price_trend(vehicle_id),
        "maintenance_by_category": db.get_maintenance_by_category(vehicle_id),
        "per_vehicle": db.get_per_vehicle_summary() if not vehicle_id else None,
        "stats": {
            "total": round(stats["total_cents"] / 100, 2),
            "this_month": round(stats["this_month_cents"] / 100, 2),
            "count": stats["count"],
            "avg_fill": round(stats["avg_cents"] / 100, 2) if stats["count"] else 0,
            "avg_price_per_unit": round(stats["avg_price_per_unit"], 3) if stats["avg_price_per_unit"] else None,
            "maintenance_total": round(stats["maintenance_total_cents"] / 100, 2),
            "cost_per_km": stats["cost_per_km"],
        },
    })


# ---- Shared receipt image serving ----

@app.route("/receipts/<path:filename>")
def receipt_image(filename):
    return send_from_directory(db.RECEIPTS_DIR, filename)


# ---- Export ----

@app.route("/export.xlsx")
def export_xlsx():
    buf = build_workbook(
        fuel_logs=db.list_fuel_logs(),
        maintenance_logs=db.list_maintenance_logs(),
        odometer_logs=db.list_odometer_logs(),
        monthly_totals=db.get_monthly_totals(months=999),
        yearly_totals=db.get_yearly_totals(),
        per_vehicle_summary=db.get_per_vehicle_summary(),
    )
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"fuelledger-{date.today().isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/export.csv")
def export_csv():
    buf = build_csv(db.list_fuel_logs())
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"fuelledger-fuel-{date.today().isoformat()}.csv",
        mimetype="text/csv",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, threaded=True)
