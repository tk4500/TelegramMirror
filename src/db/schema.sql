-- TelegramMirror - Schema do Banco de Dados
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY CHECK(id <= 2),
    phone TEXT UNIQUE NOT NULL,
    api_id INTEGER NOT NULL,
    api_hash TEXT NOT NULL,
    session_string TEXT,
    is_active INTEGER DEFAULT 1,
    is_primary INTEGER DEFAULT 0,
    status TEXT DEFAULT 'disconnected' CHECK(status IN ('connected','disconnected','banned','flood_wait')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    source_chat_id INTEGER NOT NULL,
    dest_chat_id INTEGER NOT NULL,
    last_message_id INTEGER NOT NULL DEFAULT 0,
    total_copied INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,
    mode TEXT NOT NULL CHECK(mode IN ('forward','replicate')),
    scope TEXT NOT NULL CHECK(scope IN ('new','history','checkpoint')),
    status TEXT DEFAULT 'idle' CHECK(status IN ('idle','running','paused','completed','error')),
    debug_mode INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(account_id, source_chat_id, dest_chat_id)
);

CREATE TABLE IF NOT EXISTS failed_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id INTEGER NOT NULL REFERENCES checkpoints(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL,
    error_message TEXT,
    error_type TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','retrying','resolved','abandoned')),
    original_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS replacement_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    old_value TEXT NOT NULL,
    new_value TEXT NOT NULL DEFAULT '',
    rule_type TEXT NOT NULL CHECK(rule_type IN ('link','username','text','regex')),
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS copy_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id INTEGER NOT NULL REFERENCES checkpoints(id) ON DELETE CASCADE,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    messages_processed INTEGER DEFAULT 0,
    messages_failed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running' CHECK(status IN ('running','completed','paused','error')),
    speed_profile TEXT DEFAULT 'safe' CHECK(speed_profile IN ('safe','moderate','fast'))
);

-- Índices para consultas frequentes
CREATE INDEX IF NOT EXISTS idx_checkpoints_account ON checkpoints(account_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_source ON checkpoints(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON checkpoints(status);
CREATE INDEX IF NOT EXISTS idx_failed_checkpoint ON failed_messages(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_failed_status ON failed_messages(status);
CREATE INDEX IF NOT EXISTS idx_copy_sessions_checkpoint ON copy_sessions(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_copy_sessions_status ON copy_sessions(status);
CREATE INDEX IF NOT EXISTS idx_replacement_account ON replacement_rules(account_id);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
