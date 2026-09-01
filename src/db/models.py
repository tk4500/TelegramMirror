"""Modelos Pydantic e Enums para as entidades do banco de dados do TelegramMirror."""

from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict

class AccountStatus(StrEnum):
    """Status possíveis de uma conta do Telegram."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    BANNED = "banned"
    FLOOD_WAIT = "flood_wait"

class CopyMode(StrEnum):
    """Modos de cópia disponíveis."""
    FORWARD = "forward"
    REPLICATE = "replicate"

class CopyScope(StrEnum):
    """Escopos de leitura para a cópia."""
    NEW = "new"
    HISTORY = "history"
    CHECKPOINT = "checkpoint"

class CopyStatus(StrEnum):
    """Status de uma operação de cópia/checkpoint."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"

class FailedMessageStatus(StrEnum):
    """Status de uma mensagem com falha."""
    PENDING = "pending"
    RETRYING = "retrying"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"

class SpeedProfile(StrEnum):
    """Perfis de velocidade para mitigar riscos de ban."""
    SAFE = "safe"
    MODERATE = "moderate"
    FAST = "fast"

class CopySessionStatus(StrEnum):
    """Status de uma sessão de cópia."""
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"

class RuleType(StrEnum):
    """Tipos de regras de substituição."""
    LINK = "link"
    USERNAME = "username"
    TEXT = "text"
    REGEX = "regex"

class Account(BaseModel):
    """Modelo representando uma conta do Telegram no banco de dados."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    api_id: int
    api_hash: str
    session_string: str | None = None
    is_active: bool = True
    is_primary: bool = False
    status: AccountStatus = AccountStatus.DISCONNECTED
    created_at: datetime | None = None
    updated_at: datetime | None = None

class Checkpoint(BaseModel):
    """Modelo representando o progresso de cópia entre origem e destino."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    source_chat_id: int
    dest_chat_id: int
    last_message_id: int = 0
    total_copied: int = 0
    total_failed: int = 0
    mode: CopyMode
    scope: CopyScope
    status: CopyStatus = CopyStatus.IDLE
    debug_mode: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

class FailedMessage(BaseModel):
    """Modelo representando uma mensagem que falhou no envio."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    checkpoint_id: int
    message_id: int
    error_message: str | None = None
    error_type: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    status: FailedMessageStatus = FailedMessageStatus.PENDING
    original_data: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None

class ReplacementRule(BaseModel):
    """Modelo representando uma regra de substituição de texto/links."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int | None = None
    old_value: str
    new_value: str = ""
    rule_type: RuleType
    is_active: bool = True
    created_at: datetime | None = None

class CopySession(BaseModel):
    """Modelo representando uma sessão de cópia executada."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    checkpoint_id: int
    started_at: datetime
    ended_at: datetime | None = None
    messages_processed: int = 0
    messages_failed: int = 0
    status: CopySessionStatus = CopySessionStatus.RUNNING
    speed_profile: SpeedProfile = SpeedProfile.SAFE
