# Architecture

## Overview

FuelLedger is a single Flask process backed by SQLite, with no background workers, message queue, or external services. It's designed to run as one Docker container with a bind-mounted data volume.

```
Browser (phone/desktop)
   │  HTTP (LAN / Tailscale)
   ▼
Flask app (app.py)
   │
   ├── OCR pipeline (ocr.py, crop.py) ── Tesseract + OpenCV, runs in-process
   ├── SQLite (db.py) ── /app/data/gas_tracker.db (bind-mounted, persists across rebuilds)
   ├── Receipt images ── /app/data/receipts/ (bind-mounted)
   └── Export (export.py) ── openpyxl (xlsx) / stdlib csv
```

## Data model

Three independent record-type tables, each with a required `vehicle_id` and an optional `payment_method_id`, rather than one table with a type discriminator — the field sets genuinely diverge (fuel has volume/price, maintenance has shop/category, odometer has neither), and this keeps `NOT NULL` constraints meaningful per type.

```sql
vehicles(id, name, year, make, model, fuel_type, notes, is_archived, created_at)
payment_methods(id, name, notes, is_archived, created_at)

fuel_logs(id, vehicle_id → vehicles, payment_method_id → payment_methods,
          date, amount_cents, odometer, station, volume, volume_unit,
          price_per_unit, image_filename, raw_ocr_text, confidence_json, created_at)

maintenance_logs(id, vehicle_id → vehicles, payment_method_id → payment_methods,
                  date, amount_cents, odometer, shop, category, category_other,
                  notes, image_filename, created_at)

odometer_logs(id, vehicle_id → vehicles, date, odometer, note, created_at)
```

`vehicle_id` uses `ON DELETE RESTRICT` — hard-deleting a vehicle with any history fails at the database layer, enforcing "every record belongs to a vehicle." The normal UI path for retiring a vehicle is archiving (`is_archived = 1`); true deletion is only offered once a pre-check confirms zero records exist. `payment_method_id` uses `ON DELETE SET NULL`, since payment methods are optional and independent of vehicles.

A `vehicle_timeline` SQL view unions all three record tables (recreated on every boot — views hold no data, so this is always safe):

```sql
CREATE VIEW vehicle_timeline AS
SELECT 'fuel', id, vehicle_id, date, amount_cents, odometer, station, payment_method_id, created_at FROM fuel_logs
UNION ALL
SELECT 'maintenance', id, vehicle_id, date, amount_cents, odometer, COALESCE(category_other, category), payment_method_id, created_at FROM maintenance_logs
UNION ALL
SELECT 'odometer', id, vehicle_id, date, NULL, odometer, note, NULL, created_at FROM odometer_logs;
```

This view powers both the per-vehicle timeline page and the mileage/cost-per-km calculations, since odometer readings can originate from any of the three record types.

## Migration strategy

Additive, idempotent, never destructive:

- New tables are created with `CREATE TABLE IF NOT EXISTS` on every boot (`db._create_new_schema()`).
- New columns on existing tables are added via a `PRAGMA table_info` check + `ALTER TABLE ADD COLUMN`, only for columns that don't already exist (`db.migrate_schema()`) — the same pattern used since the very first schema evolution of this project.
- The legacy single-vehicle `receipts` table (from the pre-vehicle version of this app) is migrated once (`db.migrate_legacy_receipts()`): a placeholder "My Vehicle" is created if none exists, and every row is copied into `fuel_logs`.

**Idempotency via a durable marker, not table emptiness.** Each copied row is tagged with `fuel_logs.legacy_receipt_id`, set to the original `receipts.id` — a stable, immutable key. Re-running the migration recomputes "which legacy rows are still pending" as *"every `receipts.id` not already present as a `legacy_receipt_id` in `fuel_logs`,"* rather than assuming "if `fuel_logs` has any rows, migration must already be done." That assumption is what an earlier version of this function got wrong: if `fuel_logs` ever had unrelated rows before the legacy table was migrated, the old code skipped copying entirely and renamed `receipts` away anyway, silently orphaning its rows. A partial unique index (`idx_fuel_logs_legacy_receipt_id`, created only after the column exists) is a hard backstop against ever double-importing the same legacy row.

`receipts` is renamed to `receipts_v1_backup` only once every one of its rows is confirmed represented in `fuel_logs` (a fresh count, not an assumption), and never renamed over an existing `receipts_v1_backup` — if both tables somehow exist at once, the migration logs a diagnostic and leaves both untouched rather than guessing at a merge.

## OCR pipeline

1. **Auto-crop** (`crop.py`): the uploaded photo is converted to OpenCV grayscale, edge-detected, and searched for the largest 4-point contour above a minimum area — if found, a perspective transform flattens it to a top-down crop. If no confident quadrilateral is found, the original image passes through unchanged (never a hard failure).
2. **Illumination normalization**: the grayscale crop is divided by a heavily Gaussian-blurred copy of itself (flat-fielding), cancelling shadow/glare gradients from handheld phone photos before contrast/threshold steps.
3. **Binarization**: autocontrast, a median-filter despeckle pass, then a pure-Python Otsu threshold.
4. **OCR**: Tesseract (`--oem 3 --psm 6`, tuned for a single receipt column).
5. **Field extraction**: line-scanning regex + keyword-anchoring (e.g. a dollar amount on a line containing "total" is preferred over one on a line containing "gal") extracts amount, date, station (matched against a fixed brand list, falling back to a heuristic first-line guess), volume/unit, and price per unit. Each field reports a confidence level (`high`/`low`/`none`) based on whether it was keyword-anchored or a fallback guess — surfaced in the UI so low-confidence fields get flagged for manual review before saving.

## Analytics queries

- Weekly/monthly/yearly fuel totals: SQL `strftime()` grouping.
- Year-over-year monthly comparison: grouped by `(year, month)`, reshaped in Python into a `{year: [12 months]}` matrix, capped at the most recent 4 years.
- Cost per kilometre: `(MAX(odometer) - MIN(odometer))` over `vehicle_timeline` for a vehicle, divided by summed fuel + maintenance cost over the same window — no window function needed since odometer readings are monotonically non-decreasing.
- Per-entry "distance since previous" (used on the timeline page): `LAG(odometer) OVER (ORDER BY date, odometer)` against `vehicle_timeline`.

## Charts

All charts on the analytics page are hand-built inline SVG (bar and line charts with pointer-based hover tooltips), matching the project's "no framework, no CDN" constraint — there is no charting library dependency.
