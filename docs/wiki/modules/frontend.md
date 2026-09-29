# Module: `frontend`

The `frontend` module represents the user interface. It is purposefully designed as a "zero-build" architecture to ensure maximum compatibility with PyInstaller and local Python execution.

## Responsibilities

- Render the "Ethereal Glass" Alpine.js/TailwindCSS operations dashboard.
- Provide forms for authenticating Telegram accounts, defining regex rules, and managing checkpoints.
- Display a real-time terminal of backend logs via WebSockets.

## Key Files

- `frontend/index.html` — The singular entry point containing the full DOM, Alpine.js state (`x-data="app()"`), and UI logic.
- `frontend/failed_modal.html` — An isolated template for viewing failed messages and retries.

## Internal Structure

The entire UI state is managed within a single `Alpine.data('app', ...)` object. It handles authentication state (`isAuthenticated`), navigation (`currentTab`), and WebSocket listeners that push log strings into the `serverLogs` array.

## Dependencies

- **Used by:** The browser, served statically via `src/web/app.py`.
- **Uses:** `TailwindCSS (CDN)`, `Alpine.js (CDN)`, `Alpine Focus Plugin`.

## Notable Patterns / Gotchas

- **Do Not Use Node.js:** There is no `package.json` and no build step. All CSS is either Tailwind utility classes or custom `<style>` blocks injected directly into `index.html`.
- **Ethereal Glass Elements:** Containers should utilize the custom `.ethereal-shell` and `.ethereal-core` classes defined in the `<style>` block to maintain the high-end aesthetic.
