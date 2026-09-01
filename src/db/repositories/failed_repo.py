"""Repositório para operações CRUD na tabela de mensagens com falha."""

from src.db.connection import Database
from src.db.models import FailedMessage, FailedMessageStatus
from src.utils.logger import logger

class FailedMessagesRepository:
    """Gerencia operações de banco de dados para mensagens que falharam no envio."""

    def __init__(self, db: Database):
        self._db = db

    async def create(self, failed: FailedMessage) -> int:
        """Registra uma nova mensagem com falha. Retorna o ID."""
        cursor = await self._db.execute(
            """INSERT INTO failed_messages (checkpoint_id, message_id, error_message,
               error_type, retry_count, max_retries, status, original_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (failed.checkpoint_id, failed.message_id, failed.error_message,
             failed.error_type, failed.retry_count, failed.max_retries,
             failed.status.value, failed.original_data)
        )
        logger.debug("Falha registrada para mensagem %d do checkpoint %d", failed.message_id, failed.checkpoint_id)
        return cursor.lastrowid

    async def get_by_id(self, failed_id: int) -> FailedMessage | None:
        """Busca uma mensagem com falha pelo ID."""
        row = await self._db.fetch_one("SELECT * FROM failed_messages WHERE id = ?", (failed_id,))
        return FailedMessage(**row) if row else None

    async def get_pending_by_checkpoint(self, checkpoint_id: int) -> list[FailedMessage]:
        """Retorna mensagens pendentes de retry para um checkpoint."""
        rows = await self._db.fetch_all(
            """SELECT * FROM failed_messages
               WHERE checkpoint_id = ? AND status IN ('pending', 'retrying')
               AND retry_count < max_retries ORDER BY message_id""",
            (checkpoint_id,)
        )
        return [FailedMessage(**row) for row in rows]

    async def get_all_by_checkpoint(self, checkpoint_id: int) -> list[FailedMessage]:
        """Retorna todas as falhas de um checkpoint."""
        rows = await self._db.fetch_all(
            "SELECT * FROM failed_messages WHERE checkpoint_id = ? ORDER BY message_id",
            (checkpoint_id,)
        )
        return [FailedMessage(**row) for row in rows]

    async def increment_retry(self, failed_id: int) -> None:
        """Incrementa o contador de retry e marca como 'retrying'."""
        await self._db.execute(
            """UPDATE failed_messages SET retry_count = retry_count + 1,
               status = 'retrying' WHERE id = ?""",
            (failed_id,)
        )

    async def mark_resolved(self, failed_id: int) -> None:
        """Marca uma mensagem como resolvida (enviada com sucesso no retry)."""
        await self._db.execute(
            """UPDATE failed_messages SET status = 'resolved',
               resolved_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (failed_id,)
        )

    async def mark_abandoned(self, failed_id: int) -> None:
        """Marca como abandonada (excedeu max_retries)."""
        await self._db.execute(
            """UPDATE failed_messages SET status = 'abandoned',
               resolved_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (failed_id,)
        )

    async def count_by_status(self, checkpoint_id: int, status: FailedMessageStatus) -> int:
        """Conta falhas por status para um checkpoint."""
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as total FROM failed_messages WHERE checkpoint_id = ? AND status = ?",
            (checkpoint_id, status.value)
        )
        return row["total"] if row else 0

    async def delete_resolved(self, checkpoint_id: int) -> int:
        """Remove todas as falhas resolvidas de um checkpoint. Retorna quantas foram removidas."""
        cursor = await self._db.execute(
            "DELETE FROM failed_messages WHERE checkpoint_id = ? AND status = 'resolved'",
            (checkpoint_id,)
        )
        return cursor.rowcount
