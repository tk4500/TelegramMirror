# CloneX (TelegramMirror)

CloneX is a high-performance, dark-themed operations dashboard and backend pipeline designed to seamlessly copy, customize, and mirror messages between Telegram channels and groups. Built with a focus on speed, reliability, and evasion of API limits (FloodWait), CloneX provides a centralized interface for monitoring and controlling replication workflows.

## Features

- **Real-time Mirroring:** Replicate or forward messages from source to destination chats instantly.
- **FloodWait Protection:** Intelligent speed profiles (Safe, Moderate, Fast, Insane) and dual-account fallback systems to mitigate API rate limits.
- **Message Customization:** On-the-fly replacement of URLs, mentions, and text patterns via regex rules.
- **Checkpointing System:** Automatically resumes from the exact last message after a pause, crash, or restart, preventing data loss or duplication.
- **High-End Operations Dashboard:** A premium, "Ethereal Glass" UI built with Alpine.js and TailwindCSS, offering real-time telemetry (CPU, RAM, Disk), visual log inspection, and dynamic system controls.

## Architecture & Stack

- **Backend:** Python + Telethon (for Telegram API interaction)
- **Frontend:** HTML5, Alpine.js, TailwindCSS (zero-build, embedded UI)
- **Database:** Local SQLite (`data/` directory) for configuration and checkpoint tracking.

Read more about our architectural choices in the [Decision Records (ADRs)](docs/adr/).

## Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/TelegramMirror.git
   cd TelegramMirror
   ```

2. **Set up the virtual environment & install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\\Scripts\\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Copy the example environment file and fill in your credentials.
   ```bash
   cp .env.example .env
   ```

4. **Run the Application:**
   ```bash
   python -m src.main
   ```
   The CloneX dashboard will be available at `http://localhost:port` (check your console output for the exact address).

## Build Instructions (Executable)

To bundle the application into a standalone executable using PyInstaller:

```bash
python build.py
```
Check the `dist/` directory for the compiled binaries.

## API Keys & Telegram Setup

You will need a Telegram API ID and Hash. You can obtain these by logging into [my.telegram.org](https://my.telegram.org) and creating a new application. The frontend UI provides an interface to authenticate your accounts using these credentials.

## License

MIT License. See `LICENSE` for details.
