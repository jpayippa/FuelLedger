"""Synthetic receipt image generation for OCR integration tests.

No real personal receipts are used or committed anywhere in this repo - every
image these functions produce is generated at test time from plain text.
"""

from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _font(size=24):
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


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
