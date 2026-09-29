# Getting Started

## Prerequisites

- Python 3.11+
- Git
- Two Telegram Accounts (recommended for failover)
- Telegram API ID and Hash (from my.telegram.org)

## Installation

```bash
git clone https://github.com/tarci/TelegramMirror.git
cd TelegramMirror

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
```

## First Run

To run the application with the system tray icon and open the dashboard:

```bash
python src/desktop.py
```

The UI will automatically open in your default browser at `http://127.0.0.1:8080`.

## Common Workflows

### Authenticating an Account
1. Open the **Contas do Telegram** tab.
2. Click **Autenticar Sessão** on Conta 1.
3. Enter your API ID, Hash, and International Phone Number.
4. Input the code sent to your Telegram app.

### Setting up a Cloning Pipeline
1. Open the **Clonagem** tab.
2. Select a Source chat from the left list.
3. Select a Destination chat from the right list.
4. Ensure your "Modo de Operação" is set (e.g., Replicar).
5. Click **Iniciar** on the Dashboard tab.

### Headless Server Deployment
For running on a VPS without a GUI/System Tray:
```bash
python src/server.py
```

## Configuration

- `.env` — Controls the web panel port, admin credentials, and `DEBUG_MODE`.
- `data/database.sqlite` — The generated local database where all runtime configurations (Regex rules, Checkpoints) are stored. Do not manually edit this file.

## Where to Go Next

- Architecture: [architecture.md](architecture.md)
- Module reference: [README.md#module-map](README.md#module-map)