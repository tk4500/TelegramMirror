"""
Worker de retry automático para mensagens que falharam no envio.
Reprocessa mensagens da tabela failed_messages com backoff incremental.
"""

import asyncio
from telethon import TelegramClient
from src.db.connection import Database
from src.db.repositories.failed_repo import FailedMessagesRepository
from src.db.models import FailedMessage, FailedMessageStatus
from src.services.copier.forward_copier import ForwardCopier
from src.services.copier.text_copier import TextCopier
from src.utils.logger import logger

class RetryWorker:
    """
    Worker que reprocessa mensagens com falha.
    Implementa retry com backoff incremental e limite de tentativas.
    """

    def __init__(self, client: TelegramClient, db: Database):
        self._client = client
        self._db = db
        self._failed_repo = FailedMessagesRepository(db)
        self._forward_copier = ForwardCopier(client)
        self._text_copier = TextCopier(client)
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def retry_pending(
        self,
        checkpoint_id: int,
        dest_chat_id: int,
        source_chat_id: int,
        delay: float = 3.0,
    ) -> dict:
        """
        Retenta todas as mensagens pendentes de um checkpoint.

        Args:
            checkpoint_id: ID do checkpoint.
            dest_chat_id: ID do chat de destino.
            source_chat_id: ID do chat de origem.
            delay: Delay entre cada retry (segundos).

        Returns:
            Estatísticas do retry {resolved, abandoned, remaining}.
        """
        self._is_running = True
        resolved = 0
        abandoned = 0

        pending = await self._failed_repo.get_pending_by_checkpoint(checkpoint_id)
        logger.info("Retry: %d mensagens pendentes para checkpoint %d.", len(pending), checkpoint_id)

        for failed in pending:
            if not self._is_running:
                break

            # Verifica se excedeu max_retries
            if failed.retry_count >= failed.max_retries:
                await self._failed_repo.mark_abandoned(failed.id)
                abandoned += 1
                logger.debug("Mensagem %d abandonada (max retries).", failed.message_id)
                continue

            # Incrementa retry
            await self._failed_repo.increment_retry(failed.id)

            # Tenta reenviar via forward (método mais simples)
            try:
                result = await self._forward_copier.forward_message(
                    source_chat_id, dest_chat_id, failed.message_id
                )
                if result:
                    await self._failed_repo.mark_resolved(failed.id)
                    resolved += 1
                    logger.info("Retry bem-sucedido: mensagem %d.", failed.message_id)
                else:
                    logger.warning("Retry falhou: mensagem %d não encontrada.", failed.message_id)
            except Exception as e:
                logger.error("Retry falhou para mensagem %d: %s", failed.message_id, e)

            # Backoff incremental
            backoff = delay * (failed.retry_count + 1)
            await asyncio.sleep(backoff)

        self._is_running = False

        remaining = await self._failed_repo.count_by_status(
            checkpoint_id, FailedMessageStatus.PENDING
        )

        result = {
            "resolved": resolved,
            "abandoned": abandoned,
            "remaining": remaining,
        }
        logger.info("Retry concluído para checkpoint %d: %s", checkpoint_id, result)
        return result

    async def stop(self) -> None:
        """Para o worker de retry."""
        self._is_running = False

    async def retry_single(
        self,
        failed_id: int,
        dest_chat_id: int,
        source_chat_id: int,
    ) -> bool:
        """
        Retenta uma mensagem específica.

        Returns:
            True se resolvida, False se falhou.
        """
        failed = await self._failed_repo.get_by_id(failed_id)
        if not failed:
            logger.warning("Falha %d não encontrada.", failed_id)
            return False

        if failed.status == FailedMessageStatus.RESOLVED:
            logger.debug("Mensagem %d já foi resolvida.", failed.message_id)
            return True

        await self._failed_repo.increment_retry(failed.id)

        try:
            result = await self._forward_copier.forward_message(
                source_chat_id, dest_chat_id, failed.message_id
            )
            if result:
                await self._failed_repo.mark_resolved(failed.id)
                logger.info("Retry manual bem-sucedido: mensagem %d.", failed.message_id)
                return True
        except Exception as e:
            logger.error("Retry manual falhou para mensagem %d: %s", failed.message_id, e)

        # Verifica se deve abandonar
        updated = await self._failed_repo.get_by_id(failed.id)
        if updated and updated.retry_count >= updated.max_retries:
            await self._failed_repo.mark_abandoned(failed.id)

        return False

    async def cleanup_resolved(self, checkpoint_id: int) -> int:
        """Remove falhas resolvidas do banco. Retorna quantas foram removidas."""
        count = await self._failed_repo.delete_resolved(checkpoint_id)
        logger.info("Limpeza: %d falhas resolvidas removidas do checkpoint %d.", count, checkpoint_id)
        return count
