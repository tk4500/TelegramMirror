"""
Serviço de gerenciamento de checkpoints.
Coordena a persistência do progresso de cópia e garante
que o avanço só ocorra após confirmação válida da API.
"""

import json
from src.db.connection import Database
from src.db.repositories.checkpoints_repo import CheckpointsRepository
from src.db.repositories.failed_repo import FailedMessagesRepository
from src.db.models import (
    Checkpoint, FailedMessage, CopyStatus, CopyMode,
    CopyScope, FailedMessageStatus,
)
from src.utils.logger import logger

class CheckpointService:
    """
    Serviço que gerencia checkpoints de cópia.
    Garante atomicidade: só avança o checkpoint após confirmação
    válida de entrega na API do Telegram.
    """

    def __init__(self, db: Database):
        self._db = db
        self._checkpoints_repo = CheckpointsRepository(db)
        self._failed_repo = FailedMessagesRepository(db)

    async def get_or_create_checkpoint(
        self,
        account_id: int,
        source_chat_id: int,
        dest_chat_id: int,
        mode: CopyMode,
        scope: CopyScope,
        debug_mode: bool = False,
    ) -> Checkpoint:
        """
        Busca checkpoint existente ou cria um novo para o par origem/destino.

        Returns:
            Checkpoint existente ou recém-criado.
        """
        existing = await self._checkpoints_repo.get_by_chat_pair(
            account_id, source_chat_id, dest_chat_id
        )
        if existing:
            logger.debug("Checkpoint existente encontrado (ID: %d).", existing.id)
            # Atualiza o debug_mode se for diferente
            if existing.debug_mode != debug_mode:
                await self._db.execute("UPDATE checkpoints SET debug_mode = ? WHERE id = ?", (1 if debug_mode else 0, existing.id))
                existing.debug_mode = debug_mode
            return existing

        new_checkpoint = Checkpoint(
            id=0,  # Auto-increment
            account_id=account_id,
            source_chat_id=source_chat_id,
            dest_chat_id=dest_chat_id,
            mode=mode,
            scope=scope,
            debug_mode=debug_mode,
        )
        new_id = await self._checkpoints_repo.create(new_checkpoint)
        created = await self._checkpoints_repo.get_by_id(new_id)
        logger.info(
            "Novo checkpoint criado (ID: %d) para %d -> %d.",
            new_id, source_chat_id, dest_chat_id,
        )
        return created

    async def confirm_message_sent(
        self,
        checkpoint_id: int,
        message_id: int,
    ) -> None:
        """
        Confirma que uma mensagem foi enviada com sucesso.
        Avança o checkpoint SOMENTE após confirmação válida.

        Args:
            checkpoint_id: ID do checkpoint.
            message_id: ID da mensagem confirmada.
        """
        checkpoint = await self._checkpoints_repo.get_by_id(checkpoint_id)
        if not checkpoint:
            logger.error("Checkpoint %d não encontrado.", checkpoint_id)
            return

        await self._checkpoints_repo.update_progress(
            checkpoint_id,
            last_message_id=message_id,
            total_copied=checkpoint.total_copied + 1,
            total_failed=checkpoint.total_failed,
        )
        logger.debug("Checkpoint %d avançado para mensagem %d.", checkpoint_id, message_id)

    async def register_failure(
        self,
        checkpoint_id: int,
        message_id: int,
        error: Exception,
        original_data: dict | None = None,
    ) -> None:
        """
        Registra uma falha de envio no banco.

        Args:
            checkpoint_id: ID do checkpoint.
            message_id: ID da mensagem que falhou.
            error: Exceção capturada.
            original_data: Dados originais para retry (serializado como JSON).
        """
        failed = FailedMessage(
            id=0,
            checkpoint_id=checkpoint_id,
            message_id=message_id,
            error_message=str(error),
            error_type=type(error).__name__,
            original_data=json.dumps(original_data) if original_data else None,
        )
        await self._failed_repo.create(failed)

        # Atualiza contador de falhas no checkpoint
        checkpoint = await self._checkpoints_repo.get_by_id(checkpoint_id)
        if checkpoint:
            await self._checkpoints_repo.update_progress(
                checkpoint_id,
                last_message_id=checkpoint.last_message_id,
                total_copied=checkpoint.total_copied,
                total_failed=checkpoint.total_failed + 1,
            )

        logger.warning(
            "Falha registrada: mensagem %d do checkpoint %d (%s: %s)",
            message_id, checkpoint_id, type(error).__name__, error,
        )

    async def update_status(self, checkpoint_id: int, status: CopyStatus) -> None:
        """Atualiza o status do checkpoint."""
        await self._checkpoints_repo.update_status(checkpoint_id, status)

    async def reset_checkpoint(self, checkpoint_id: int) -> None:
        """Reseta o checkpoint para o início."""
        await self._checkpoints_repo.reset(checkpoint_id)
        logger.info("Checkpoint %d resetado.", checkpoint_id)

    async def set_checkpoint_position(self, checkpoint_id: int, message_id: int) -> None:
        """Altera manualmente a posição do checkpoint."""
        await self._checkpoints_repo.set_position(checkpoint_id, message_id)

    async def get_stats(self, checkpoint_id: int) -> dict:
        """Retorna estatísticas do checkpoint."""
        checkpoint = await self._checkpoints_repo.get_by_id(checkpoint_id)
        if not checkpoint:
            return {}

        pending_failures = await self._failed_repo.count_by_status(
            checkpoint_id, FailedMessageStatus.PENDING
        )
        resolved_failures = await self._failed_repo.count_by_status(
            checkpoint_id, FailedMessageStatus.RESOLVED
        )

        return {
            "checkpoint_id": checkpoint.id,
            "last_message_id": checkpoint.last_message_id,
            "total_copied": checkpoint.total_copied,
            "total_failed": checkpoint.total_failed,
            "pending_retries": pending_failures,
            "resolved_retries": resolved_failures,
            "status": checkpoint.status.value,
            "mode": checkpoint.mode.value,
            "scope": checkpoint.scope.value,
        }
