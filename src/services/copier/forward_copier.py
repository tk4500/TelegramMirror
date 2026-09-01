"""
Módulo de cópia por forward nativo do Telegram.
Utiliza a função forward_messages do Telethon para encaminhar
mensagens preservando o cabeçalho original de encaminhamento.
"""

from src.utils.logger import log_execution
from telethon import TelegramClient
from telethon.errors import (
    ChatForwardsRestrictedError,
    FloodWaitError,
    MessageIdInvalidError,
    ChannelPrivateError,
)
from telethon.tl.types import Message
import asyncio
from src.utils.logger import logger

class ForwardCopier:
    """
    Copia mensagens usando o forward nativo do Telegram.
    Preserva o cabeçalho 'Encaminhado de...' na mensagem.
    """

    @log_execution
    def __init__(self, client: TelegramClient):
        self._client = client

    @log_execution
    async def forward_message(
        self,
        source_chat_id: int,
        dest_chat_id: int,
        message_id: int,
    ) -> Message | None:
        """
        Encaminha uma única mensagem da origem para o destino.

        Args:
            source_chat_id: ID do chat de origem.
            dest_chat_id: ID do chat de destino.
            message_id: ID da mensagem a encaminhar.

        Returns:
            Mensagem encaminhada ou None se falhou.

        Raises:
            ChatForwardsRestrictedError: Se o chat não permite encaminhamento.
            ChannelPrivateError: Se não tem acesso ao canal.
        """
        try:
            result = await self._client.forward_messages(
                entity=dest_chat_id,
                messages=message_id,
                from_peer=source_chat_id,
            )
            if isinstance(result, list):
                msg = result[0] if result else None
            else:
                msg = result
            logger.debug(
                "Mensagem %d encaminhada de %d para %d.",
                message_id, source_chat_id, dest_chat_id,
            )
            return msg
        except ChatForwardsRestrictedError:
            logger.warning(
                "Chat %d não permite encaminhamento. Use o modo Replicar.",
                source_chat_id,
            )
            raise
        except MessageIdInvalidError:
            logger.warning("Mensagem %d não encontrada no chat %d.", message_id, source_chat_id)
            return None
        except FloodWaitError as e:
            logger.warning("FloodWait ao encaminhar: aguardar %ds.", e.seconds)
            raise
        except ChannelPrivateError:
            logger.error("Sem acesso ao canal %d ou %d.", source_chat_id, dest_chat_id)
            raise

    @log_execution
    async def forward_messages_batch(
        self,
        source_chat_id: int,
        dest_chat_id: int,
        message_ids: list[int],
        delay: float = 0.5,
    ) -> list[Message | None]:
        """
        Encaminha múltiplas mensagens em lote com delay entre cada uma.

        Args:
            source_chat_id: ID do chat de origem.
            dest_chat_id: ID do chat de destino.
            message_ids: Lista de IDs de mensagens a encaminhar.
            delay: Delay em segundos entre cada forward (anti-flood).

        Returns:
            Lista de mensagens encaminhadas (None para as que falharam).
        """
        results: list[Message | None] = []

        for msg_id in message_ids:
            try:
                result = await self.forward_message(
                    source_chat_id, dest_chat_id, msg_id
                )
                results.append(result)
            except FloodWaitError as e:
                logger.warning("FloodWait no batch: aguardando %ds.", e.seconds)
                await asyncio.sleep(e.seconds)
                # Retenta após esperar
                try:
                    result = await self.forward_message(
                        source_chat_id, dest_chat_id, msg_id
                    )
                    results.append(result)
                except Exception:
                    results.append(None)
            except (ChatForwardsRestrictedError, ChannelPrivateError):
                # Erros irrecuperáveis — para o batch inteiro
                logger.error("Erro irrecuperável no batch de forward. Interrompendo.")
                results.extend([None] * (len(message_ids) - len(results)))
                break
            except Exception as e:
                logger.error("Erro ao encaminhar mensagem %d: %s", msg_id, e)
                results.append(None)

            if delay > 0:
                await asyncio.sleep(delay)

        logger.info(
            "Batch forward concluído: %d/%d mensagens encaminhadas.",
            sum(1 for r in results if r is not None),
            len(message_ids),
        )
        return results

    @log_execution
    async def can_forward(self, chat_id: int) -> bool:
        """
        Verifica se um chat permite encaminhamento de mensagens.

        Returns:
            True se o chat permite forward, False caso contrário.
        """
        try:
            entity = await self._client.get_entity(chat_id)
            # Channels/supergroups podem ter noforwards habilitado
            if hasattr(entity, "noforwards"):
                return not entity.noforwards
            return True
        except Exception as e:
            logger.warning("Erro ao verificar permissão de forward para %d: %s", chat_id, e)
            return False
