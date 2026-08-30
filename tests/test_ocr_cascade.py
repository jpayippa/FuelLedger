"""Deterministic tests for run_ocr()'s fallback cascade - monkeypatches the
single Tesseract seam (ocr._run_tesseract_pass) so behavior doesn't depend on
real Tesseract quirks. See tests/test_ocr_integration.py for proof the real
Tesseract path still resolves on the first attempt for known-good input."""

import ocr
from tests.ocr_fixtures import CLEAN_FUEL_RECEIPT, make_synthetic_receipt

VALID_TEXT = "TOTAL $43.75\nDATE: 08/15/2026"
INVALID_TEXT = "THANK YOU FOR SHOPPING"

_IMAGE = make_synthetic_receipt(CLEAN_FUEL_RECEIPT)


def _canned(monkeypatch, results_by_attempt):
    """Returns the list of psm values passed to each successive call, in
    order - a stand-in for "which cascade attempts actually ran"."""
    calls = []

    def fake_run_tesseract_pass(image, psm):
        calls.append(psm)
        return results_by_attempt[len(calls) - 1]

    monkeypatch.setattr(ocr, "_run_tesseract_pass", fake_run_tesseract_pass)
    return calls


def test_first_attempt_validates_stops_immediately(monkeypatch):
    calls = _canned(monkeypatch, [(VALID_TEXT, 90.0)])
    text, _ = ocr.run_ocr(_IMAGE)
    assert text == VALID_TEXT
    assert calls == [psm for _, psm in ocr.CASCADE_ATTEMPTS[:1]]


def test_second_attempt_validates_after_first_fails(monkeypatch):
    calls = _canned(monkeypatch, [(INVALID_TEXT, 40.0), (VALID_TEXT, 85.0)])
    text, _ = ocr.run_ocr(_IMAGE)
    assert text == VALID_TEXT
    assert calls == [psm for _, psm in ocr.CASCADE_ATTEMPTS[:2]]


def test_no_attempt_validates_returns_first_attempt_text(monkeypatch):
    calls = _canned(
        monkeypatch,
        [(INVALID_TEXT, 40.0), ("STILL NOTHING", 35.0), ("NOPE", 30.0)],
    )
    text, _ = ocr.run_ocr(_IMAGE)
    assert text == INVALID_TEXT
    assert calls == [psm for _, psm in ocr.CASCADE_ATTEMPTS]
