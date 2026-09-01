"""Serviço para listagem e categorização de chats do Telegram."""

from dataclasses import dataclass, field
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User
from src.utils.logger import logger

@dataclass
class ChatInfo:
    """Informações de um chat do Telegram para exibição no painel."""
    id: int
    title: str
    chat_type: str  # 'channel', 'group', 'supergroup'
    username: str | None = None
    participants_count: int | None = None
    photo_id: int | None = None
    is_public: bool = False
    access_hash: int | None = None

class ChatService:
    """
    Serviço responsável por listar e categorizar os chats
    acessíveis pela conta ativa do Telegram.
    """

    def __init__(self, client: TelegramClient):
        self._client = client

    async def get_all_chats(self) -> list[ChatInfo]:
        """
        Busca todos os canais e grupos acessíveis da conta ativa.
        Filtra apenas Channel e Chat (ignora conversas privadas/bots).

        Returns:
            Lista de ChatInfo ordenada por título.
        """
        chats: list[ChatInfo] = []

        async for dialog in self._client.iter_dialogs():
            entity = dialog.entity

            if isinstance(entity, Channel):
                chat_type = "channel" if entity.broadcast else "supergroup"
                chat_info = ChatInfo(
                    id=entity.id,
                    title=entity.title or "",
                    chat_type=chat_type,
                    username=entity.username,
                    participants_count=getattr(entity, "participants_count", None),
                    photo_id=getattr(entity.photo, "photo_id", None) if entity.photo else None,
                    is_public=bool(entity.username),
                    access_hash=entity.access_hash,
                )
                chats.append(chat_info)

            elif isinstance(entity, Chat):
                chat_info = ChatInfo(
                    id=entity.id,
                    title=entity.title or "",
                    chat_type="group",
                    participants_count=getattr(entity, "participants_count", None),
                    photo_id=getattr(entity.photo, "photo_id", None) if entity.photo else None,
                    is_public=False,
                )
                chats.append(chat_info)

        chats.sort(key=lambda c: c.title.lower())
        logger.info("Listados %d chats (canais/grupos) da conta ativa.", len(chats))
        return chats

    async def get_chat_by_id(self, chat_id: int) -> ChatInfo | None:
        """Busca um chat específico pelo ID."""
        try:
            entity = await self._client.get_entity(chat_id)
            if isinstance(entity, Channel):
                chat_type = "channel" if entity.broadcast else "supergroup"
                return ChatInfo(
                    id=entity.id,
                    title=entity.title or "",
                    chat_type=chat_type,
                    username=entity.username,
                    participants_count=getattr(entity, "participants_count", None),
                    photo_id=getattr(entity.photo, "photo_id", None) if entity.photo else None,
                    is_public=bool(entity.username),
                    access_hash=entity.access_hash,
                )
            elif isinstance(entity, Chat):
                return ChatInfo(
                    id=entity.id,
                    title=entity.title or "",
                    chat_type="group",
                    participants_count=getattr(entity, "participants_count", None),
                    photo_id=getattr(entity.photo, "photo_id", None) if entity.photo else None,
                    is_public=False,
                )
        except Exception as e:
            logger.error("Erro ao buscar chat %d: %s", chat_id, e)
        return None

    async def search_chats(self, query: str) -> list[ChatInfo]:
        """Filtra chats pelo título (busca local, case-insensitive)."""
        all_chats = await self.get_all_chats()
        query_lower = query.lower()
        return [c for c in all_chats if query_lower in c.title.lower()]

    async def get_channels(self) -> list[ChatInfo]:
        """Retorna apenas os canais."""
        all_chats = await self.get_all_chats()
        return [c for c in all_chats if c.chat_type == "channel"]

    async def get_groups(self) -> list[ChatInfo]:
        """Retorna apenas os grupos (incluindo supergrupos)."""
        all_chats = await self.get_all_chats()
        return [c for c in all_chats if c.chat_type in ("group", "supergroup")]
