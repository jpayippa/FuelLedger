import re
from datetime import date, datetime

import pytesseract
from dateutil import parser as dateparser
from PIL import Image, ImageFilter, ImageOps

MONEY_RE = re.compile(r"(?<!\d)\$?\s?(\d{1,4}\.\d{2})(?!\d)")
TOTAL_KEYWORDS = re.compile(r"\b(total|amount due|amount|sale|charged|balance due|grand total)\b", re.I)
EXCLUDE_LINE = re.compile(
    r"\b(gal|gallon|price\s*/?\s*gal|ppg|per\s*gal|auth|ref\s*#?|acct|account|card|term|seq|pump\s*#?|approval)\b",
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
    img = img.convert("L")

    w, h = img.size
    max_dim = max(w, h)
    if max_dim > 2000:
        scale = 2000 / max_dim
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    elif max_dim < 1200:
        scale = 1600 / max_dim
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    threshold = _otsu_threshold(img)
    img = img.point(lambda p: 255 if p > threshold else 0)
    return img


def run_ocr(image):
    processed = preprocess_for_ocr(image)
    return pytesseract.image_to_string(processed, lang="eng", config="--oem 3 --psm 6")


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
        return None
    keyworded = [c for c in candidates if c[0]]
    pool = keyworded or candidates
    return max(pool, key=lambda c: c[1])[1]


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
    return max(candidates) if candidates else None


def parse_receipt(image):
    text = run_ocr(image)
    return {
        "amount": extract_amount(text),
        "date": extract_date(text),
        "raw_text": text,
    }
