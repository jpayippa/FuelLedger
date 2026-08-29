# FuelLedger

A privacy-first, self-hosted vehicle expense tracker. Scan fuel receipts with your phone, log maintenance and odometer checkpoints, and see spend trends across your whole fleet — all processed locally, with no cloud services involved.

## Overview

FuelLedger is a mobile-first web app for tracking everything you spend on your vehicles:

- **Fuel** — scan a receipt with your phone camera; local OCR (Tesseract + OpenCV) extracts the date, amount, station, volume, and price per unit automatically, with an editable review step and per-field confidence highlighting before anything is saved.
- **Maintenance** — date, cost, shop, category (oil change, tires, brakes, etc.), and odometer reading, with an optional receipt scan to prefill date/cost.
- **Odometer checkpoints** — simple entries to build a continuous mileage history.
- **Multiple vehicles**, each with its own history, and **payment methods** tracked independently and optionally attached to any record.
- **Analytics** — per-vehicle totals, monthly/weekly spend, average fill-up, average price per unit, maintenance cost by category, cost per kilometre, and year-over-year comparisons, all rendered as hand-built SVG charts (no chart library, no CDN).
- **A full timeline view** per vehicle, merging fuel, maintenance, and odometer history into one chronological feed.
- **Excel and CSV export**, including a multi-sheet workbook with monthly/yearly/per-vehicle summary tabs.
- **Installable as a PWA** with offline app-shell caching, and a light/dark theme toggle.

## Screenshots

_TODO: add screenshots of the home screen, fuel scan/review flow, timeline, and analytics dashboard here._

| Home | Analytics | Timeline |
|------|-----------|----------|
| _placeholder_ | _placeholder_ | _placeholder_ |

## Privacy

FuelLedger is built to keep your data yours:

- **All OCR runs locally** in the container, via Tesseract and OpenCV — no receipt image or extracted text is ever sent to a third-party API.
- **No telemetry, no analytics, no external network calls** of any kind at runtime.
- **All data lives in your own SQLite database and local filesystem**, inside the Docker volume you control. Nothing leaves your server.
- **You own your export path**: every record can be exported to Excel or CSV at any time, so your data is never locked in.
- The app ships with **no authentication by default**, on the assumption it runs on a trusted home network or behind your own reverse proxy/VPN (e.g. Tailscale). See [SECURITY.md](SECURITY.md) before exposing it beyond that.

## Architecture

- **Backend**: Python (Flask), server-rendered Jinja templates + vanilla JavaScript — no frontend framework, no build step.
- **Database**: SQLite, plain `sqlite3` (no ORM). Vehicles, payment methods, and three record-type tables (fuel, maintenance, odometer) are independent tables joined by a `vehicle_timeline` SQL view for the combined history and mileage calculations.
- **OCR pipeline**: an uploaded photo is perspective-corrected and cropped (OpenCV contour detection), illumination-normalized to cancel shadows/glare, then binarized and passed to Tesseract; regex + keyword-anchored heuristics extract structured fields with a per-field confidence score.
- **Charts**: hand-rolled inline SVG bar/line charts with hover tooltips — no chart library or external CDN.
- See [docs/architecture.md](docs/architecture.md) for the full schema and migration design.

## Stack

- Python 3, Flask
- SQLite (stdlib `sqlite3`)
- Tesseract OCR (`pytesseract`) + OpenCV (`opencv-python-headless`) + Pillow
- openpyxl (Excel export)
- Vanilla JS, Jinja2, hand-written CSS — no frontend framework or build tooling
- Docker / Docker Compose for deployment

## Install & run locally

```bash
git clone https://github.com/<your-username>/FuelLedger.git
cd FuelLedger
pip install -r requirements.txt
python app.py
```

The app will listen on port 80 by default (override by editing `app.py`'s `app.run(...)` call or running behind a reverse proxy). Tesseract must be installed on the host (`apt install tesseract-ocr` on Debian/Ubuntu) if not running via Docker.

## Docker deployment

FuelLedger is built as a single image and deployed via Compose with one bind-mounted data volume so your database and receipt images survive rebuilds:

```bash
# Build the image
docker build -t fuelledger:latest .

# deploy/docker-compose.yml (adjust the host path to taste)
services:
  fuelledger:
    image: fuelledger:latest
    container_name: fuelledger
    restart: unless-stopped
    ports:
      - "8080:80"
    environment:
      - TZ=America/Toronto
    volumes:
      - ./data:/app/data

docker compose up -d
```

Open `http://<host>:8080`, add your first vehicle under **Manage**, and start logging.

### Upgrading from a pre-vehicle install

If you're upgrading from an earlier single-vehicle version, the app migrates your existing fuel data automatically and safely on first boot: it creates a placeholder "My Vehicle" vehicle, copies every existing fuel record onto it, and keeps your original table around as a backup (`receipts_v1_backup`) rather than deleting it. The migration is idempotent — safe to restart the container as many times as you like.

## Documentation

- [docs/architecture.md](docs/architecture.md) — schema, migration design, and query approach for analytics
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- [SECURITY.md](SECURITY.md) — threat model and how to report a vulnerability

## Development

Built with the assistance of AI pair-programming tooling (Claude Code) as a development accelerant — all design decisions, review, and commits are the maintainer's own.

## License

[MIT](LICENSE)
