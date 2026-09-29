# ADR-001: Ethereal Glass Frontend Architecture

## Status
Accepted

## Date
2026-09-29

## Context
The CloneX (TelegramMirror) project required an operations dashboard to manage complex cloning pipelines, monitor system health, and authenticate Telegram sessions. Key requirements:
- Must run locally as a zero-build, embedded UI served directly by the Python backend.
- Requires high-performance reactivity for real-time telemetry (WebSocket logs, CPU/RAM stats).
- Must project a premium, high-end "Agency-Tier" aesthetic (dark mode, glassmorphism) to match the tool's advanced capabilities.
- Needs to be highly maintainable within a single `index.html` file without a complex Node.js build step.

## Decision
We elected to use **Alpine.js** coupled with **TailwindCSS (via CDN)** for the frontend stack, implementing an **"Ethereal Glass"** visual architecture.

## Alternatives Considered

### React / Next.js
- **Pros:** Robust ecosystem, excellent componentization.
- **Cons:** Requires a heavy Node.js build pipeline (`npm install`, `npm run build`), which complicates deployment for a tool meant to be compiled into a standalone Python executable via PyInstaller.
- **Rejected:** Overkill for a single-page local dashboard; breaks the zero-dependency Python deployment model.

### Vanilla HTML / CSS / JS
- **Pros:** Zero dependencies, fastest initial load.
- **Cons:** Managing WebSocket state, complex DOM updates for the log terminal, and multi-tab state management becomes brittle and verbose.
- **Rejected:** Insufficient for the highly reactive, state-driven nature of the dashboard.

### Bootstrap / Traditional CSS Frameworks
- **Pros:** Familiar, rapid prototyping.
- **Cons:** Results in a generic, "admin-panel" look. Achieving the specific "High-End Visual Design" (custom cubic-beziers, backdrop-blur, precise typography scaling) requires fighting the framework.
- **Rejected:** Fails the aesthetic and premium feel requirements.

## Consequences

- **Zero-Build Pipeline:** The entire frontend lives in `frontend/index.html` and is served statically by the Python backend. It requires no `package.json` or build steps, making PyInstaller bundling seamless.
- **Reactivity:** Alpine.js provides Vue-like reactivity (`x-data`, `x-show`, `@click`) in a lightweight script tag, perfectly handling the WebSocket log streams and tab state.
- **Premium Aesthetic:** By leveraging TailwindCSS via CDN and injecting custom CSS for `cubic-bezier` transitions, `backdrop-blur`, and the "Double-Bezel" (Doppelrand) card structure, the UI achieves an Awwwards-tier "Ethereal Glass" look without heavy assets.
- **Trade-off:** Using Tailwind via CDN is generally discouraged for large production sites due to file size, but is perfectly acceptable for a locally-served Python dashboard where network latency is zero.
