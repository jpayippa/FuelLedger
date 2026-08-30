import os
import re
import threading
from datetime import date, datetime

import pytesseract
from dateutil import parser as dateparser
from PIL import Image, ImageFilter, ImageOps

import crop

OCR_MAX_CONCURRENCY = int(os.environ.get("OCR_MAX_CONCURRENCY", "1"))
OCR_SEMAPHORE_TIMEOUT_SECONDS = int(os.environ.get("OCR_SEMAPHORE_TIMEOUT_SECONDS", "30"))
_ocr_semaphore = threading.Semaphore(OCR_MAX_CONCURRENCY)


class OcrBusyError(Exception):
    pass


MONEY_RE = re.compile(r"(?<!\d)\$?\s?(\d{1,4}\.\d{2})(?!\d)")
TOTAL_KEYWORDS = re.compile(r"\b(total|amount due|amount|sale|charged|balance due|grand total)\b", re.I)
EXCLUDE_LINE = re.compile(
    r"\b(gal|gallon|litre|liter|price\s*/?\s*(gal|l)|ppg|ppl|per\s*(gal|l)|auth|ref\s*#?|acct|account|card|term|seq|pump\s*#?|approval)\b",
    re.I,
)

_MONTH = r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?"
DATE_CANDIDATE_RE = re.compile(
    rf"(\d{{1,2}}[/\-.]\d{{1,2}}[/\-.]\d{{2,4}})"
    rf"|(\d{{4}}[/\-]\d{{1,2}}[/\-]\d{{1,2}})"
    rf"|({_MONTH}\s+\d{{1,2}},?\s+\d{{2,4}})"
    rf"|(\d{{1,2}}\s+{_MONTH},?\s+\d{{2,4}})",
    re.IGNORECASE,
)

VOLUME_RE = re.compile(r"(?<!\d)(\d{1,3}\.\d{2,3})\s*(LITRE|LITER|GALLON|GAL|L)S?", re.I)
PRICE_PER_UNIT_KEYWORDS = re.compile(r"\b(price\s*/?\s*(gal|l)|ppg|ppl|per\s*(gal|l)|unit\s*price)\b", re.I)
PRICE_PER_UNIT_RE = re.compile(r"(?<!\d)(\d\.\d{3})(?!\d)")

STATION_BRANDS = [
    "PETRO-CANADA", "PETRO CANADA", "ESSO", "SHELL", "HUSKY", "ULTRAMAR",
    "CIRCLE K", "COSTCO", "PIONEER", "MOBIL", "CHEVRON", "EXXON", "BP",
    "SUNOCO", "IRVING", "CO-OP", "CANADIAN TIRE", "SEVEN ELEVEN", "7-ELEVEN",
    "FLYING J", "PILOT", "MARATHON", "SPEEDWAY", "VALERO", "ARCO", "CENEX",
]

_ADDRESS_HINT = re.compile(r"\d{2,}|www\.|\.com|@", re.I)
_BOILERPLATE_LINE = re.compile(
    r"^(transaction record|sales (receipt|record)|customer('s)? copy|merchant copy|"
    r"duplicate receipt|tax invoice|invoice|receipt)$",
    re.I,
)

CARD_LAST4_RE = re.compile(r"\*{2,}\s?(\d{4})\b")
CARD_BRAND_RE = re.compile(r"\b(VISA|MASTERCARD|MASTER CARD|AMEX|AMERICAN EXPRESS|DISCOVER|DEBIT)\b", re.I)
CASH_RE = re.compile(r"(?<!PRICE )(?<!DISCOUNT )\bCASH\b(?!\s*(PRICE|DISCOUNT|BACK))", re.I)
_NON_CARD_ID_LINE = re.compile(
    r"\b(terminal|trans(action)?\s*#?|store\s*#?|ref(erence)?\s*#?|auth\s*#?|seq\s*#?|invoice\s*#?)\b",
    re.I,
)


def _otsu_threshold(img):
    hist = img.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_bg = weight_bg = 0
    max_var, threshold = 0.0, 128
    for i, h in enumerate(hist):
        weight_bg += h
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * h
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        var_between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var_between > max_var:
            max_var, threshold = var_between, i
    return threshold


def preprocess_for_ocr(image):
    img = ImageOps.exif_transpose(image)
    img = crop.auto_crop(img)
    img = img.convert("L")

    w, h = img.size
    max_dim = max(w, h)
    if max_dim > 2000:
        scale = 2000 / max_dim
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    elif max_dim < 1200:
        scale = 1600 / max_dim
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    img = crop.normalize_illumination(img)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    threshold = _otsu_threshold(img)
    img = img.point(lambda p: 255 if p > threshold else 0)
    return img


def run_ocr(image):
    if not _ocr_semaphore.acquire(timeout=OCR_SEMAPHORE_TIMEOUT_SECONDS):
        raise OcrBusyError("The server is busy processing another receipt. Please try again shortly.")
    try:
        processed = preprocess_for_ocr(image)
        return pytesseract.image_to_string(processed, lang="eng", config="--oem 3 --psm 6")
    finally:
        _ocr_semaphore.release()


def extract_amount(text):
    candidates = []
    for line in text.splitlines():
        if EXCLUDE_LINE.search(line):
            continue
        for m in MONEY_RE.finditer(line):
            amount = float(m.group(1))
            if 0 < amount <= 999.99:
                candidates.append((bool(TOTAL_KEYWORDS.search(line)), amount))
    if not candidates:
        return None, "none"
    keyworded = [c for c in candidates if c[0]]
    pool = keyworded or candidates
    value = max(pool, key=lambda c: c[1])[1]
    confidence = "high" if keyworded else "low"
    return value, confidence


def extract_date(text, today=None):
    today = today or date.today()
    candidates = []
    for m in DATE_CANDIDATE_RE.finditer(text):
        raw = next(g for g in m.groups() if g)
        try:
            parsed = dateparser.parse(raw, default=datetime(today.year, 1, 1)).date()
        except (ValueError, OverflowError):
            continue
        if parsed > today or parsed.year < today.year - 2:
            continue
        candidates.append(parsed)
    if not candidates:
        return None, "none"
    confidence = "high" if len(set(candidates)) == 1 else "low"
    return max(candidates), confidence


def extract_station(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    upper_text = re.sub(r"\s*-\s*", "-", text.upper())
    for brand in STATION_BRANDS:
        if brand in upper_text:
            return brand.title(), "high"

    for line in lines[:6]:
        if _ADDRESS_HINT.search(line) or _BOILERPLATE_LINE.match(line.strip()):
            continue
        if 3 <= len(line) <= 40 and not any(ch.isdigit() for ch in line):
            return line.title(), "low"

    return None, "none"


def extract_volume_and_unit(text):
    candidates = []
    for line in text.splitlines():
        for m in VOLUME_RE.finditer(line):
            value = float(m.group(1))
            unit_raw = m.group(2).upper()
            unit = "L" if unit_raw.startswith("L") else "gal"
            if 0 < value <= 500:
                candidates.append((value, unit))
    if not candidates:
        return None, None, "none"
    value, unit = candidates[0]
    confidence = "high" if len(candidates) == 1 else "low"
    return value, unit, confidence


def extract_price_per_unit(text):
    candidates = []
    for line in text.splitlines():
        has_keyword = bool(PRICE_PER_UNIT_KEYWORDS.search(line))
        for m in PRICE_PER_UNIT_RE.finditer(line):
            value = float(m.group(1))
            if 0.3 <= value <= 5.0:
                candidates.append((has_keyword, value))
    if not candidates:
        return None, "none"
    keyworded = [c for c in candidates if c[0]]
    pool = keyworded or candidates
    value = pool[0][1]
    confidence = "high" if keyworded and len(keyworded) == 1 else ("low" if pool else "none")
    return value, confidence


def extract_payment_hint(text):
    candidates = []
    for line in text.splitlines():
        if _NON_CARD_ID_LINE.search(line):
            continue
        m = CARD_LAST4_RE.search(line)
        if not m:
            continue
        brand_m = CARD_BRAND_RE.search(line) or CARD_BRAND_RE.search(text)
        candidates.append((bool(CARD_BRAND_RE.search(line)), m.group(1), brand_m))

    if candidates:
        candidates.sort(key=lambda c: not c[0])  # prefer a match on a line naming the brand
        _, last4, brand_m = candidates[0]
        return {
            "method": "card",
            "card_last4": last4,
            "brand": brand_m.group(1).title() if brand_m else None,
        }
    if CASH_RE.search(text):
        return {"method": "cash", "card_last4": None, "brand": None}
    return {"method": None, "card_last4": None, "brand": None}


def parse_receipt(image):
    text = run_ocr(image)

    amount, amount_conf = extract_amount(text)
    txn_date, date_conf = extract_date(text)
    station, station_conf = extract_station(text)
    volume, volume_unit, volume_conf = extract_volume_and_unit(text)
    price_per_unit, price_conf = extract_price_per_unit(text)
    payment_hint = extract_payment_hint(text)

    return {
        "amount": amount,
        "date": txn_date,
        "station": station,
        "volume": volume,
        "volume_unit": volume_unit,
        "price_per_unit": price_per_unit,
        "payment_hint": payment_hint,
        "raw_text": text,
        "confidence": {
            "amount": amount_conf,
            "date": date_conf,
            "station": station_conf,
            "volume": volume_conf,
            "price_per_unit": price_conf,
        },
    }
