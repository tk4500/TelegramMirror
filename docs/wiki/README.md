# TelegramMirror Code Wiki

Welcome to the internal documentation for **TelegramMirror** (also known as CloneX).

TelegramMirror is a high-performance, resilient pipeline built to securely copy, customize, and forward messages between Telegram channels and groups. It operates locally or on a VPS via a standalone Python backend (Telethon) and an embedded, zero-build Alpine/Tailwind frontend.

## Key Concepts

- **FloodWait Avoidance** — Implements multi-account failover and tunable speed profiles to respect Telegram's rate limits.
- **Checkpointing** — Every successful operation is logged to SQLite so pipelines can resume exactly where they left off after a restart or crash.
- **On-the-fly Transformation** — Links, mentions, and text can be dynamically swapped using regex configurations before the payload reaches the destination.
- **Headless & Desktop Modes** — Can run as a system tray application (`desktop.py`) for standard users or a pure API (`server.py`) for VPS deployment.

## Entry Points

- [`src/server.py`](https://github.com/tarci/TelegramMirror/blob/main/src/server.py) — The headless server entry point (FastAPI over Uvicorn).
- [`src/desktop.py`](https://github.com/tarci/TelegramMirror/blob/main/src/desktop.py) — The desktop entry point featuring a PyStray system tray.
- [`src/core/orchestrator.py`](https://github.com/tarci/TelegramMirror/blob/main/src/core/orchestrator.py) — The main orchestrator that governs the task loop, checkpoints, and transformer.
- [`frontend/index.html`](https://github.com/tarci/TelegramMirror/blob/main/frontend/index.html) — The fully-contained, zero-build Alpine.js UI.

## High-Level Architecture

The system uses `Telethon` to maintain persistent Telegram client sessions. Requests to start a cloning flow hit the FastAPI endpoints in `src/web/`, which dispatch tasks to `src/core/orchestrator.py`. The orchestrator pulls history via `src/services/history/`, transforms the data, and writes the output back via `src/services/copier/`. State and checkpointing are flushed to a local SQLite database in `src/db/`.

See [architecture.md](architecture.md).

## Module Map

| Module | Purpose |
|---|---|
| [`core`](modules/core.md) | Orchestration, Telethon session management, and rate-limit failovers. |
| [`web`](modules/web.md) | FastAPI controllers, WebSocket log streaming, and system endpoints. |
| [`services`](modules/services.md) | Granular business logic: copying, history extraction, downloading, and regex transformation. |
| [`db`](modules/db.md) | SQLite connection pool, schema, and repository layer for checkpoints. |
| [`frontend`](modules/frontend.md) | The static "Ethereal Glass" operations dashboard. |

## Getting Started

See [getting-started.md](getting-started.md).