"""Repositório para operações CRUD na tabela de checkpoints."""

from src.db.connection import Database
from src.db.models import Checkpoint, CopyStatus
from src.utils.logger import logger

class CheckpointsRepository:
    """Gerencia operações de banco de dados para checkpoints de cópia."""

    def __init__(self, db: Database):
        self._db = db

    async def create(self, checkpoint: Checkpoint) -> int:
        """Cria um novo checkpoint. Retorna o ID gerado."""
        cursor = await self._db.execute(
            """INSERT INTO checkpoints (account_id, source_chat_id, dest_chat_id,
               last_message_id, total_copied, total_failed, mode, scope, status, debug_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (checkpoint.account_id, checkpoint.source_chat_id, checkpoint.dest_chat_id,
             checkpoint.last_message_id, checkpoint.total_copied, checkpoint.total_failed,
             checkpoint.mode.value, checkpoint.scope.value, checkpoint.status.value,
             1 if checkpoint.debug_mode else 0)
        )
        logger.info("Checkpoint criado para %d -> %d", checkpoint.source_chat_id, checkpoint.dest_chat_id)
        return cursor.lastrowid

    async def get_by_id(self, checkpoint_id: int) -> Checkpoint | None:
        """Busca um checkpoint pelo ID."""
        row = await self._db.fetch_one("SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,))
        return Checkpoint(**row) if row else None

    async def get_by_chat_pair(self, account_id: int, source_chat_id: int, dest_chat_id: int) -> Checkpoint | None:
        """Busca checkpoint pelo par origem/destino de uma conta."""
        row = await self._db.fetch_one(
            """SELECT * FROM checkpoints
               WHERE account_id = ? AND source_chat_id = ? AND dest_chat_id = ?""",
            (account_id, source_chat_id, dest_chat_id)
        )
        return Checkpoint(**row) if row else None

    async def get_all_by_account(self, account_id: int) -> list[Checkpoint]:
        """Retorna todos os checkpoints de uma conta."""
        rows = await self._db.fetch_all(
            "SELECT * FROM checkpoints WHERE account_id = ? ORDER BY id", (account_id,)
        )
        return [Checkpoint(**row) for row in rows]

    async def update_progress(self, checkpoint_id: int, last_message_id: int, total_copied: int, total_failed: int) -> None:
        """Atualiza o progresso de um checkpoint após processar uma mensagem."""
        await self._db.execute(
            """UPDATE checkpoints SET last_message_id = ?, total_copied = ?,
               total_failed = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (last_message_id, total_copied, total_failed, checkpoint_id)
        )

    async def update_status(self, checkpoint_id: int, status: CopyStatus) -> None:
        """Atualiza o status de um checkpoint."""
        await self._db.execute(
            "UPDATE checkpoints SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status.value, checkpoint_id)
        )

    async def reset(self, checkpoint_id: int) -> None:
        """Reseta um checkpoint para o início (last_message_id=0, contadores zerados)."""
        await self._db.execute(
            """UPDATE checkpoints SET last_message_id = 0, total_copied = 0,
               total_failed = 0, status = 'idle', updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (checkpoint_id,)
        )
        logger.info("Checkpoint %d resetado.", checkpoint_id)

    async def set_position(self, checkpoint_id: int, message_id: int) -> None:
        """Altera manualmente a posição do checkpoint."""
        await self._db.execute(
            "UPDATE checkpoints SET last_message_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (message_id, checkpoint_id)
        )
        logger.info("Checkpoint %d reposicionado para mensagem %d.", checkpoint_id, message_id)

    async def delete(self, checkpoint_id: int) -> None:
        """Remove um checkpoint pelo ID."""
        await self._db.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
