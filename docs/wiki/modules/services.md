# Module: `services`

The `services` module contains the granular business logic of the application. The orchestrator delegates specific actions (like extracting history or mutating strings) to these isolated, stateless classes.

## Responsibilities

- Fetching historical messages from Telegram chats in chunks.
- Applying user-defined regex replacements to message text.
- Executing the physical forwarding or replication (cloning) of messages to destination chats.
- Providing retry wrappers for transient failures.

## Key Files

- `src/services/history_service.py` — Extracts batches of messages from a source ID.
- `src/services/transformer.py` — Applies regex rules defined in the database.
- `src/services/copier/message_copier.py` — The core logic deciding how to replicate a message (handling media, albums, polls, etc.).
- `src/services/checkpoint_service.py` — Interface for interacting with the database to get/set the current sync marker.

## Internal Structure

Most services are designed as static helper classes or lightweight instances. They receive a `TelegramClient` reference passed down from the Orchestrator.

## Dependencies

- **Used by:** `src/core/orchestrator.py`
- **Uses:** `src/db/models.py`, `Telethon`

## Notable Patterns / Gotchas

- **Media Handling:** `message_copier.py` contains complex logic for dealing with Telegram Albums (grouped media). Telegram returns albums as separate messages with a shared `grouped_id`. The copier must buffer these and send them as a single operation.
