# Security Policy

## Threat model

FuelLedger is designed to be self-hosted on a **trusted local network** (home LAN, or a private overlay network like Tailscale). By default:

- There is **no authentication or authorization** — anyone who can reach the app's port can view and modify all data.
- There is **no rate limiting or CSRF protection**.
- The bundled Flask server runs in development mode (`app.run(...)`), which is fine for a personal home-network deployment but is explicitly not hardened for adversarial traffic.
- OCR and image processing run against user-uploaded files locally; while Pillow/OpenCV/Tesseract are mature libraries, no image-processing stack is immune to malformed-input bugs, so this app should not be exposed to untrusted uploaders.

**Do not expose FuelLedger directly to the public internet.** If you need remote access, put it behind:
- A VPN or overlay network (Tailscale, WireGuard), or
- A reverse proxy that adds authentication (e.g. an `oauth2-proxy` or Basic Auth in nginx/Caddy in front of it).

## Data handling

- All data (SQLite database, receipt/invoice images) stays on the host machine, inside the bind-mounted `data/` volume. Nothing is transmitted elsewhere.
- Uploaded receipt images are re-encoded (stripping EXIF/GPS metadata) before being stored.
- There is no built-in backup mechanism — back up the `data/` directory using your own tooling.

## Reporting a vulnerability

This is a small personal/hobby project without a dedicated security team. If you find a vulnerability:

1. Please open a GitHub issue marked clearly as a security concern, or, for anything sensitive, contact the maintainer directly through their GitHub profile rather than filing a public issue.
2. Include steps to reproduce and the potential impact.
3. Given the project's scope, response time is best-effort, not guaranteed.

## Supported versions

Only the latest tagged release is supported. There is no long-term-support branch.
