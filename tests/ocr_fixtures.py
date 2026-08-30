"""Synthetic receipt image generation for OCR integration tests.

No real personal receipts are used or committed anywhere in this repo - every
image these functions produce is generated at test time from plain text.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _font(size=24):
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def make_blurry(image, radius=8):
    return image.filter(ImageFilter.GaussianBlur(radius))


def make_dark(image, factor=0.15):
    arr = np.array(image.convert("L")).astype("float32") * factor
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGB")


def make_overexposed(image, factor=3.0, offset=150):
    arr = np.array(image.convert("L")).astype("float32") * factor + offset
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGB")


def make_realistic_receipt_photo(lines, receipt_size=(500, 700), canvas_size=(700, 900), background_gray=120):
    """Unlike make_synthetic_receipt (a plain white canvas with no
    surrounding background), this places the receipt on a contrasting
    mid-gray background - giving crop.auto_crop an actual boundary to
    detect, and keeping overall brightness moderate instead of overexposed.
    Used specifically for testing "a normal photo produces no quality
    warnings," where make_synthetic_receipt's plain-white full-frame style
    would legitimately (and correctly) trip both the overexposed and
    boundary-not-detected checks."""
    canvas = Image.new("L", canvas_size, color=background_gray)
    receipt = Image.new("L", receipt_size, color=250)
    draw = ImageDraw.Draw(receipt)
    font = _font(20)
    y = 20
    for line in lines:
        draw.text((15, y), line, fill=10, font=font)
        y += 30
    offset = ((canvas_size[0] - receipt_size[0]) // 2, (canvas_size[1] - receipt_size[1]) // 2)
    canvas.paste(receipt, offset)
    return canvas.convert("RGB")


def make_synthetic_receipt(lines, size=(600, 800)):
    """Render `lines` as a plain white receipt image with black monospace text,
    matching the fixed layout used for manual verification during development."""
    img = Image.new("L", size, color=255)
    draw = ImageDraw.Draw(img)
    font = _font(24)
    y = 30
    for line in lines:
        draw.text((30, y), line, fill=0, font=font)
        y += 36
    return img.convert("RGB")


CLEAN_FUEL_RECEIPT = [
    "SHELL GAS STATION",
    "123 MAIN ST",
    "",
    "DATE: 08/15/2026   TIME: 14:32",
    "PUMP #3",
    "",
    "UNLEADED",
    "GALLONS      12.503",
    "PRICE/GAL    3.499",
    "FUEL TOTAL   $43.75",
    "",
    "TAX          $0.00",
    "TOTAL        $43.75",
    "",
    "VISA ****1234",
    "AUTH# 00123456",
    "THANK YOU",
]

BOILERPLATE_HEADER_RECEIPT = [
    "TRANSACTION RECORD",
    "MORAVIAN STORE & GAS",
    "14787 SELTON LINE",
    "THAMESVILLE",
    "",
    "DATE: 2026-08-20  TIME: 09:14",
    "PUMP #5",
    "",
    "REGULAR",
    "VOLUME       38.452 L",
    "PRICE/L      1.539",
    "FUEL TOTAL   $59.19",
    "TAX          $0.00",
    "TOTAL        $59.19",
    "",
    "TERMINAL: ****4723",
    "MASTERCARD ****2401",
    "THANK YOU",
]

CASH_RECEIPT = [
    "ESSO STATION",
    "TERMINAL: ****8888",
    "TRANS #: 000222",
    "DATE: 08/21/2026",
    "TOTAL   $20.00",
    "TENDER: CASH",
    "THANK YOU",
]
