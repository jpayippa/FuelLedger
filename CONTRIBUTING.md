# Contributing to FuelLedger

Thanks for your interest in improving FuelLedger. This is a small, self-hosted personal project, so the process is intentionally lightweight.

## Ground rules

- **Privacy first.** Any contribution that adds a network call to a third-party service (cloud OCR, analytics, telemetry, etc.) will not be merged. The whole point of this project is that your data never leaves your server.
- **Keep it lightweight.** No frontend framework, no build step, no chart library/CDN, no heavyweight dependencies unless there's a very strong reason. Vanilla JS + Jinja + hand-rolled SVG is the house style.
- **Don't break existing data.** Any schema change must be an additive, idempotent migration (see `db.py`'s `migrate_schema`/`migrate_legacy_receipts` for the existing pattern) — never a destructive one that could lose a user's history.

## Getting set up

```bash
git clone https://github.com/<your-username>/FuelLedger.git
cd FuelLedger
pip install -r requirements.txt
# Tesseract must be installed locally for OCR to work outside Docker:
#   apt install tesseract-ocr
python app.py
```

Or just use Docker (`docker build -t fuelledger:latest .` then `docker compose up -d`) — see the README for the full compose file.

## Making a change

1. Open an issue first for anything non-trivial, so we can agree on approach before you spend time on it.
2. Keep pull requests focused — one feature or fix per PR.
3. Test your change manually against a real (or synthetic) receipt image where OCR is involved; there's no automated test suite yet, so manual verification matters.
4. Run the linter before submitting: `ruff check .`
5. Make sure `docker build` still succeeds.

## Reporting bugs / requesting features

Use the issue templates — they'll prompt for the information that's actually useful (steps to reproduce, environment, etc.).

## Code style

- Python: follow the existing style in the codebase (plain functions, no classes unless there's a clear reason, minimal comments — code should be self-explanatory).
- No comments explaining *what* code does; only *why*, when the reason isn't obvious from reading it.
