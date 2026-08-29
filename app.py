import io
import os
import uuid
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from PIL import Image

import db
import ocr
from export import build_workbook

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
        "raw_text": result["raw_text"],
    })


@app.route("/save", methods=["POST"])
def save():
    file = request.files.get("receipt")
    date_str = request.form.get("date", "")
    amount_str = request.form.get("amount", "")
    raw_text = request.form.get("raw_text", "")

    try:
        validate_date(date_str)
        amount_cents = cents_from_amount(amount_str)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid date or amount"}), 400

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

    new_id = db.insert_receipt(date_str, amount_cents, image_filename, raw_text)
    return jsonify({"id": new_id})


@app.route("/api/receipts")
def api_receipts():
    receipts = receipts_with_dollars()
    total_cents = db.get_total_cents()
    return jsonify({"receipts": receipts, "total": round(total_cents / 100, 2)})


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
    for r in receipts:
        r["amount_cents"] = r["amount_cents"]
    total_cents = db.get_total_cents()
    buf = build_workbook(receipts, total_cents)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"gas-receipts-{date.today().isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, threaded=True)
