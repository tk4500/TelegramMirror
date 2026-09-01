"""
Parser de entidades de formatação do Telegram.
Extrai e reconstrói MessageEntities para o modo Replicar,
preservando toda a formatação original da mensagem.
"""

from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityUnderline,
    MessageEntityStrike,
    MessageEntitySpoiler,
    MessageEntityTextUrl,
    MessageEntityMention,
    MessageEntityMentionName,
    MessageEntityUrl,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntityCustomEmoji,
    MessageEntityBlockquote,
    MessageEntityHashtag,
    MessageEntityBotCommand,
    MessageEntityEmail,
    MessageEntityPhone,
    TypeMessageEntity,
)
from telethon.tl.types import Message
from dataclasses import dataclass
from src.utils.logger import logger

@dataclass
class ParsedMessage:
    """Mensagem parseada com texto e entidades separados."""
    text: str
    entities: list[TypeMessageEntity]
    has_media: bool = False
    media: object | None = None
    grouped_id: int | None = None
    is_pinned: bool = False
    reply_to_msg_id: int | None = None

class EntityParser:
    """
    Parser que extrai entidades de uma mensagem do Telegram
    e permite reconstruí-las para re-envio no modo Replicar.
    """

    @staticmethod
    def parse_message(message: Message) -> ParsedMessage:
        """
        Extrai texto, entidades e metadados de uma mensagem Telegram.

        Args:
            message: Objeto Message do Telethon.

        Returns:
            ParsedMessage com todos os dados extraídos.
        """
        text = message.message or message.text or ""
        entities = list(message.entities or [])

        return ParsedMessage(
            text=text,
            entities=entities,
            has_media=message.media is not None,
            media=message.media,
            grouped_id=message.grouped_id,
            is_pinned=getattr(message, "pinned", False),
            reply_to_msg_id=getattr(message.reply_to, "reply_to_msg_id", None) if message.reply_to else None,
        )

    @staticmethod
    def clone_entities(entities: list[TypeMessageEntity], preserve_custom_emojis: bool = False) -> list[TypeMessageEntity]:
        """
        Clona a lista de entidades para evitar mutação do original.
        Reconstrói cada entidade mantendo todos os atributos.
        """
        cloned = []
        for entity in entities:
            if isinstance(entity, MessageEntityBold):
                cloned.append(MessageEntityBold(offset=entity.offset, length=entity.length))
            elif isinstance(entity, MessageEntityItalic):
                cloned.append(MessageEntityItalic(offset=entity.offset, length=entity.length))
            elif isinstance(entity, MessageEntityUnderline):
                cloned.append(MessageEntityUnderline(offset=entity.offset, length=entity.length))
            elif isinstance(entity, MessageEntityStrike):
                cloned.append(MessageEntityStrike(offset=entity.offset, length=entity.length))
            elif isinstance(entity, MessageEntitySpoiler):
                cloned.append(MessageEntitySpoiler(offset=entity.offset, length=entity.length))
            elif isinstance(entity, MessageEntityCode):
                cloned.append(MessageEntityCode(offset=entity.offset, length=entity.length))
            elif isinstance(entity, MessageEntityPre):
                cloned.append(MessageEntityPre(
                    offset=entity.offset, length=entity.length, language=entity.language or ""
                ))
            elif isinstance(entity, MessageEntityTextUrl):
                cloned.append(MessageEntityTextUrl(
                    offset=entity.offset, length=entity.length, url=entity.url
                ))
            elif isinstance(entity, MessageEntityMentionName):
                cloned.append(MessageEntityMentionName(
                    offset=entity.offset, length=entity.length, user_id=entity.user_id
                ))
            elif isinstance(entity, MessageEntityCustomEmoji):
                if not preserve_custom_emojis:
                    # Se for copiar com conta sem Premium, o envio de CustomEmoji pode falhar.
                    # Removemos a entidade, o texto bruto fallback (normalmente o próprio emoji em texto plano ou a descrição dele)
                    # se manterá na string original, mas não tentará invocar a renderização customizada proibida.
                    continue
                cloned.append(MessageEntityCustomEmoji(
                    offset=entity.offset, length=entity.length, document_id=entity.document_id
                ))
            elif isinstance(entity, MessageEntityBlockquote):
                cloned.append(MessageEntityBlockquote(offset=entity.offset, length=entity.length))
            elif isinstance(entity, (MessageEntityMention, MessageEntityUrl,
                                     MessageEntityHashtag, MessageEntityBotCommand,
                                     MessageEntityEmail, MessageEntityPhone)):
                # Entidades simples (offset + length)
                cloned.append(type(entity)(offset=entity.offset, length=entity.length))
            else:
                # Tipo desconhecido — tenta clonar genérico
                try:
                    cloned.append(type(entity)(offset=entity.offset, length=entity.length))
                except Exception:
                    logger.warning("Entidade não clonável: %s", type(entity).__name__)
        return cloned

    @staticmethod
    def entities_to_dict(entities: list[TypeMessageEntity]) -> list[dict]:
        """Converte entidades para formato dict (para serialização/debug)."""
        result = []
        for entity in entities:
            entry = {
                "type": type(entity).__name__,
                "offset": entity.offset,
                "length": entity.length,
            }
            if isinstance(entity, MessageEntityTextUrl):
                entry["url"] = entity.url
            elif isinstance(entity, MessageEntityMentionName):
                entry["user_id"] = entity.user_id
            elif isinstance(entity, MessageEntityPre):
                entry["language"] = entity.language
            elif isinstance(entity, MessageEntityCustomEmoji):
                entry["document_id"] = entity.document_id
            result.append(entry)
        return result

    @staticmethod
    def has_formatting(message: Message) -> bool:
        """Verifica se a mensagem tem alguma formatação/entidade."""
        return bool(message.entities)
