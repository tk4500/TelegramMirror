"""
Serviço para sincronização de mensagens fixadas (pinned messages).
Detecta mensagens fixadas na origem e aplica a fixação no destino.
"""

from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.tl.functions.messages import UpdatePinnedMessageRequest
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    MessageIdInvalidError,
)
from src.utils.logger import logger

class PinService:
    """
    Gerencia a sincronização de mensagens fixadas entre chats.
    Detecta pins na origem e replica a fixação no destino.
    """

    def __init__(self, client: TelegramClient):
        self._client = client

    async def pin_message(
        self,
        chat_id: int,
        message_id: int,
        notify: bool = False,
    ) -> bool:
        """
        Fixa uma mensagem em um chat.

        Args:
            chat_id: ID do chat onde fixar.
            message_id: ID da mensagem a fixar.
            notify: Se True, envia notificação aos membros.

        Returns:
            True se fixou com sucesso, False caso contrário.
        """
        try:
            await self._client(UpdatePinnedMessageRequest(
                peer=chat_id,
                id=message_id,
                silent=not notify,
            ))
            logger.info("Mensagem %d fixada no chat %d.", message_id, chat_id)
            return True
        except ChatAdminRequiredError:
            logger.warning(
                "Sem permissão de admin para fixar mensagem no chat %d.", chat_id
            )
            return False
        except MessageIdInvalidError:
            logger.warning("Mensagem %d não encontrada no chat %d.", message_id, chat_id)
            return False
        except FloodWaitError:
            raise
        except Exception as e:
            logger.error("Erro ao fixar mensagem %d no chat %d: %s", message_id, chat_id, e)
            return False

    async def unpin_message(self, chat_id: int, message_id: int) -> bool:
        """Desfixa uma mensagem específica de um chat."""
        try:
            await self._client(UpdatePinnedMessageRequest(
                peer=chat_id,
                id=message_id,
                unpin=True,
            ))
            logger.info("Mensagem %d desfixada do chat %d.", message_id, chat_id)
            return True
        except Exception as e:
            logger.error("Erro ao desfixar mensagem %d: %s", message_id, e)
            return False

    @staticmethod
    def is_pinned(message: Message) -> bool:
        """Verifica se uma mensagem está fixada."""
        return getattr(message, "pinned", False)

    async def sync_pin(
        self,
        source_message: Message,
        dest_message_id: int,
        dest_chat_id: int,
    ) -> bool:
        """
        Sincroniza o status de fixação: se a mensagem original está fixada,
        fixa a mensagem correspondente no destino.

        Args:
            source_message: Mensagem original (para verificar se está pinned).
            dest_message_id: ID da mensagem replicada/encaminhada no destino.
            dest_chat_id: ID do chat de destino.

        Returns:
            True se sincronizou (ou não era necessário), False se falhou.
        """
        if not self.is_pinned(source_message):
            return True  # Não está fixada, nada a fazer

        logger.info(
            "Mensagem %d está fixada na origem. Fixando %d no destino %d.",
            source_message.id, dest_message_id, dest_chat_id,
        )
        return await self.pin_message(dest_chat_id, dest_message_id, notify=False)

    async def get_pinned_messages(self, chat_id: int) -> list[Message]:
        """
        Busca todas as mensagens fixadas de um chat.

        Returns:
            Lista de mensagens fixadas.
        """
        pinned = []
        try:
            async for msg in self._client.iter_messages(chat_id, filter=None):
                if getattr(msg, "pinned", False):
                    pinned.append(msg)
        except Exception as e:
            logger.error("Erro ao buscar mensagens fixadas do chat %d: %s", chat_id, e)

        logger.debug("Encontradas %d mensagens fixadas no chat %d.", len(pinned), chat_id)
        return pinned
