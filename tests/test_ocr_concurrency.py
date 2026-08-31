import threading
import time

import ocr
from tests.ocr_fixtures import CLEAN_FUEL_RECEIPT, make_synthetic_receipt


def test_concurrent_ocr_calls_are_serialized(monkeypatch):
    """Two run_ocr() calls at OCR_MAX_CONCURRENCY=1 must never execute their
    'Tesseract' step at the same time - proven by a shared counter that would
    exceed 1 if they overlapped."""
    monkeypatch.setattr(ocr, "_ocr_semaphore", threading.Semaphore(1))

    active = {"count": 0, "max_seen": 0}
    lock = threading.Lock()

    def fake_run_tesseract_pass(image, psm):
        with lock:
            active["count"] += 1
            active["max_seen"] = max(active["max_seen"], active["count"])
        time.sleep(0.2)
        with lock:
            active["count"] -= 1
        return "fake ocr text", 90.0

    monkeypatch.setattr(ocr, "_run_tesseract_pass", fake_run_tesseract_pass)

    image = make_synthetic_receipt(CLEAN_FUEL_RECEIPT)
    results = []
    threads = [threading.Thread(target=lambda: results.append(ocr.run_ocr(image))) for _ in range(2)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    assert active["max_seen"] == 1, "two OCR calls ran concurrently despite OCR_MAX_CONCURRENCY=1"
    assert elapsed >= 0.4, "calls completed faster than serial execution should allow"
    assert len(results) == 2


def test_busy_error_raised_when_semaphore_exhausted(monkeypatch):
    monkeypatch.setattr(ocr, "_ocr_semaphore", threading.Semaphore(1))
    monkeypatch.setattr(ocr, "OCR_SEMAPHORE_TIMEOUT_SECONDS", 0.1)

    holder_ready = threading.Event()
    release_holder = threading.Event()

    def hold_semaphore():
        ocr._ocr_semaphore.acquire()
        holder_ready.set()
        release_holder.wait(timeout=5)
        ocr._ocr_semaphore.release()

    holder = threading.Thread(target=hold_semaphore)
    holder.start()
    holder_ready.wait(timeout=5)

    image = make_synthetic_receipt(CLEAN_FUEL_RECEIPT)
    start = time.monotonic()
    try:
        raised = False
        try:
            ocr.run_ocr(image)
        except ocr.OcrBusyError:
            raised = True
        elapsed = time.monotonic() - start
        assert raised, "expected OcrBusyError when semaphore was held past the timeout"
        assert elapsed < 2, "should fail fast at the configured timeout, not hang"
    finally:
        release_holder.set()
        holder.join(timeout=5)
