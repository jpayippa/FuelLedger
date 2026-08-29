import json
import os
import uuid
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from PIL import Image

import db
import ocr
from export import build_csv, build_workbook

app = Flask(__name__)
db.init_db()


def cents_from_amount(amount_str):
    amount = float(amount_str)
    if not (0 < amount <= 999.99):
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


def receipts_with_dollars():
    receipts = db.list_receipts()
    for r in receipts:
        r["amount"] = round(r["amount_cents"] / 100, 2)
    return receipts


@app.route("/")
def index():
    receipts = receipts_with_dollars()
    total_cents = db.get_total_cents()
    return render_template(
        "index.html",
        receipts=receipts,
        total=round(total_cents / 100, 2),
        today=date.today().isoformat(),
    )


@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


@app.route("/scan", methods=["POST"])
def scan():
    file = request.files.get("receipt")
    if not file:
        return jsonify({"error": "no file uploaded"}), 400
    try:
        image = Image.open(file.stream)
        image.load()
    except Exception:
        return jsonify({"error": "could not read image"}), 400

    result = ocr.parse_receipt(image)

    return jsonify({
        "amount": result["amount"],
        "date": result["date"].isoformat() if result["date"] else None,
        "station": result["station"],
        "volume": result["volume"],
        "volume_unit": result["volume_unit"],
        "price_per_unit": result["price_per_unit"],
        "raw_text": result["raw_text"],
        "confidence": result["confidence"],
    })


@app.route("/save", methods=["POST"])
def save():
    file = request.files.get("receipt")
    date_str = request.form.get("date", "")
    amount_str = request.form.get("amount", "")
    raw_text = request.form.get("raw_text", "")
    station = request.form.get("station") or None
    try:
        confidence = json.loads(request.form.get("confidence") or "null")
    except ValueError:
        confidence = None

    try:
        validate_date(date_str)
        amount_cents = cents_from_amount(amount_str)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid date or amount"}), 400

    volume = optional_float(request.form.get("volume"), max_val=500)
    volume_unit = request.form.get("volume_unit") or None
    if volume_unit not in ("L", "gal"):
        volume_unit = None
    price_per_unit = optional_float(request.form.get("price_per_unit"), max_val=10)

    image_filename = None
    if file:
        try:
            image = Image.open(file.stream)
            image = image.convert("RGB")
            image.thumbnail((2000, 2000), Image.LANCZOS)
            image_filename = f"{uuid.uuid4()}.jpg"
            image.save(os.path.join(db.RECEIPTS_DIR, image_filename), "JPEG", quality=85)
        except Exception:
            image_filename = None

    new_id = db.insert_receipt(
        date_str, amount_cents, image_filename, raw_text,
        station=station, volume=volume, volume_unit=volume_unit,
        price_per_unit=price_per_unit, confidence=confidence,
    )
    return jsonify({"id": new_id})


@app.route("/api/receipts")
def api_receipts():
    receipts = receipts_with_dollars()
    total_cents = db.get_total_cents()
    return jsonify({"receipts": receipts, "total": round(total_cents / 100, 2)})


@app.route("/api/analytics")
def api_analytics():
    stats = db.get_summary_stats()
    return jsonify({
        "weekly": db.get_weekly_totals(),
        "monthly": db.get_monthly_totals(),
        "yearly": db.get_yearly_totals(),
        "year_month_matrix": db.get_year_month_matrix(),
        "price_trend": db.get_price_trend(),
        "stats": {
            "total": round(stats["total_cents"] / 100, 2),
            "this_month": round(stats["this_month_cents"] / 100, 2),
            "count": stats["count"],
            "avg_fill": round(stats["avg_cents"] / 100, 2) if stats["count"] else 0,
            "avg_price_per_unit": round(stats["avg_price_per_unit"], 3) if stats["avg_price_per_unit"] else None,
        },
    })


@app.route("/delete/<int:receipt_id>", methods=["POST"])
def delete(receipt_id):
    image_filename = db.delete_receipt(receipt_id)
    if image_filename:
        path = os.path.join(db.RECEIPTS_DIR, image_filename)
        if os.path.exists(path):
            os.remove(path)
    return jsonify({"ok": True})


@app.route("/receipts/<path:filename>")
def receipt_image(filename):
    return send_from_directory(db.RECEIPTS_DIR, filename)


@app.route("/export.xlsx")
def export_xlsx():
    receipts = db.list_receipts()
    total_cents = db.get_total_cents()
    buf = build_workbook(receipts, total_cents, db.get_monthly_totals(months=999), db.get_yearly_totals())
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"gas-receipts-{date.today().isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/export.csv")
def export_csv():
    receipts = db.list_receipts()
    total_cents = db.get_total_cents()
    buf = build_csv(receipts, total_cents)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"gas-receipts-{date.today().isoformat()}.csv",
        mimetype="text/csv",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, threaded=True)
