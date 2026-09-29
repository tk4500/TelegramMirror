# CloneX (TelegramMirror) — Agent Instructions

CloneX is a high-performance Telegram message cloning and forwarding pipeline with an embedded "Ethereal Glass" Alpine.js/Tailwind frontend and a Telethon Python backend. 

Repository: https://github.com/yourusername/TelegramMirror.git

## Project layout

- `src/core/` — Telethon logic, pipelines, session and engine management.
- `src/web/` — FastAPI routes and WebSocket event streams.
- `src/db/` — Local SQLite operations and configuration stores.
- `src/services/` — Heavy worker tasks and standalone processes.
- `frontend/` — Zero-build static UI (Alpine + Tailwind CDN). Main entry is `index.html`.
- `assets/` — Icons and branding files for the executable.

## Dev environment

- **Python:** Requires Python 3.11+
- **Database:** Local SQLite (stored in `data/`, automatically initialized).
- **Environment:** Requires a `.env` file (copy from `.env.example`).
- **Dependencies:** `pip install -r requirements.txt`

## Build & test

- **Run UI/Desktop mode (System Tray):**
  ```bash
  python src/desktop.py
  ```
- **Run Headless mode (Server/VPS):**
  ```bash
  python src/server.py
  ```
- **Compile to `.exe`:**
  ```bash
  python build.py
  ```
*(# verify once tests scaffold exists: no explicit test suite found in the current tree)*

## Conventions

- **Frontend:** Zero-build. Do NOT use `npm install`, Webpack, or Node.js. All UI changes must be made directly in `frontend/index.html` using Tailwind utility classes and Alpine `x-data`/`x-show` bindings.
- **Frontend Aesthetic:** The project mandates an "Ethereal Glass" / Linear-tier high-end dark mode design. Use `Geist` font, `backdrop-blur-2xl`, translucent `bg-white/5` surfaces, and highly tuned `cubic-bezier` transitions.
- **Backend Logging:** The app uses extensive structured logging via WebSockets pushed directly to the frontend's "Monitor" tab.

## Pitfalls

- **Do NOT introduce frontend build steps.** The frontend must remain statically servable via the Python FastAPI app to ensure PyInstaller bundling works.
- **FloodWait Limits:** Telegram heavily restricts aggressive actions. Any new mirroring logic must respect the configured `speed_profile` delays.
- **Debug Mode:** `DEBUG_MODE=true` in `.env` triggers massive local console output. Avoid committing this as `true`.
