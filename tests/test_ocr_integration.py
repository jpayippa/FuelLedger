"""End-to-end tests through the real Tesseract binary against fixed synthetic
images. Slower and more environment-sensitive than test_ocr_extraction.py, so
kept to a small number and marked so they can be run/skipped separately.
Assertions reflect what Tesseract actually produces on these specific fixed
inputs - if a Tesseract upgrade changes that output, these should fail loudly
rather than be loosened to paper over it."""

import pytest

import ocr
from tests.ocr_fixtures import (
    BOILERPLATE_HEADER_RECEIPT,
    CASH_RECEIPT,
    CLEAN_FUEL_RECEIPT,
    make_synthetic_receipt,
)

pytestmark = pytest.mark.ocr_integration


def test_clean_fuel_receipt_end_to_end():
    image = make_synthetic_receipt(CLEAN_FUEL_RECEIPT)
    result = ocr.parse_receipt(image)

    assert result["amount"] == 43.75
    assert result["confidence"]["amount"] == "high"
    assert result["date"].isoformat() == "2026-08-15"
    assert result["payment_hint"]["method"] == "card"
    assert result["payment_hint"]["card_last4"] == "1234"


def test_boilerplate_header_receipt_finds_real_station_and_card():
    image = make_synthetic_receipt(BOILERPLATE_HEADER_RECEIPT)
    result = ocr.parse_receipt(image)

    assert result["amount"] == 59.19
    assert result["station"] == "Moravian Store & Gas"
    assert result["volume"] == 38.452
    assert result["volume_unit"] == "L"
    assert result["price_per_unit"] == 1.539
    # the TERMINAL id must not be reported as the card
    assert result["payment_hint"]["card_last4"] != "4723"


def test_cash_receipt_end_to_end():
    image = make_synthetic_receipt(CASH_RECEIPT)
    result = ocr.parse_receipt(image)

    assert result["amount"] == 20.00
    assert result["payment_hint"]["method"] == "cash"
