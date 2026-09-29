# Module: `core`

The `core` module is the beating heart of TelegramMirror. It handles the raw connections to Telegram, coordinates task execution, and provides safety boundaries (like rate limiting and failovers) around external API calls.

## Responsibilities

- Initialize and persist MTProto `Telethon` sessions.
- Manage the main async worker loops for processing messages.
- Transparently switch active accounts when a `FloodWait` limit is encountered.

## Key Files

- `src/core/orchestrator.py` — The main `Orchestrator` class that loops through history, calls transformers, and executes copies.
- `src/core/session_manager.py` — The `SessionManager` class that initializes and holds references to the `TelegramClient` instances.
- `src/core/failover.py` — Logic to catch rate limits and seamlessly swap the active client reference inside the session manager.

## Internal Structure

The `Orchestrator` acts as a state machine. It is initialized by the FastAPI endpoints, reads from the `CheckpointService`, and then spins up an `asyncio` task that runs until stopped, paused, or finished.

## Dependencies

- **Used by:** `src/web/api_orchestrator.py`, `src/desktop.py`
- **Uses:** `src/services/*`, `src/db/*`, `Telethon`

## Notable Patterns / Gotchas

- **Shared State:** The `SessionManager` is typically treated as a singleton initialized at startup. Do not create multiple instances of it, or you will encounter SQLite database locking errors from Telethon's internal session files.
- **Task Cancellation:** The orchestrator loop must be gracefully cancellable. Avoid placing blocking synchronous calls inside `orchestrator.py` without offloading them to a thread pool.