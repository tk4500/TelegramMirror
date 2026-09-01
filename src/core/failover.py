"""
Módulo auxiliar de failover com constantes e utilitários para
controle de alternância entre contas do Telegram.
"""

from enum import StrEnum

class FailoverReason(StrEnum):
    """Motivos que disparam o failover automático."""
    FLOOD_WAIT_LONG = "flood_wait_long"
    AUTH_KEY_ERROR = "auth_key_error"
    USER_BANNED = "user_banned"
    SESSION_REVOKED = "session_revoked"
    CONNECTION_FAILED = "connection_failed"
    MANUAL = "manual"

# Tempo máximo de FloodWait (em segundos) antes de tentar failover
FLOOD_WAIT_THRESHOLD = 60

# Número máximo de tentativas de reconexão antes de failover
MAX_RECONNECT_ATTEMPTS = 3

# Backoff base para reconexão (2^attempt seconds)
RECONNECT_BACKOFF_BASE = 2

class FailoverEvent:
    """Representa um evento de failover para logging/auditoria."""

    def __init__(
        self,
        from_account: int,
        to_account: int,
        reason: FailoverReason,
        error_message: str = "",
    ):
        self.from_account = from_account
        self.to_account = to_account
        self.reason = reason
        self.error_message = error_message

    def __repr__(self) -> str:
        return (
            f"FailoverEvent(from={self.from_account}, to={self.to_account}, "
            f"reason={self.reason}, error={self.error_message!r})"
        )
