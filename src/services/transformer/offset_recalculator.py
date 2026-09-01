"""
Utilitário para recálculo de offsets de entidades do Telegram
após modificações no texto da mensagem.
"""

from telethon.tl.types import TypeMessageEntity
from src.utils.logger import logger

class OffsetRecalculator:
    """
    Recalcula offsets de entidades do Telegram quando o texto
    é modificado (substituições, inserções, remoções).
    """

    @staticmethod
    def recalculate_after_insert(
        entities: list[TypeMessageEntity],
        position: int,
        inserted_length: int,
    ) -> list[TypeMessageEntity]:
        """
        Recalcula offsets após inserção de texto em uma posição.

        Args:
            entities: Entidades originais.
            position: Posição onde o texto foi inserido.
            inserted_length: Quantidade de caracteres inseridos.
        """
        for entity in entities:
            if entity.offset >= position:
                entity.offset += inserted_length
            elif entity.offset + entity.length > position:
                entity.length += inserted_length
        return entities

    @staticmethod
    def recalculate_after_delete(
        entities: list[TypeMessageEntity],
        position: int,
        deleted_length: int,
    ) -> list[TypeMessageEntity]:
        """
        Recalcula offsets após remoção de texto em uma posição.
        Remove entidades que ficaram com tamanho zero ou negativo.
        """
        result = []
        delete_end = position + deleted_length

        for entity in entities:
            e_start = entity.offset
            e_end = e_start + entity.length

            if e_end <= position:
                # Antes da remoção
                result.append(entity)
            elif e_start >= delete_end:
                # Depois da remoção
                entity.offset -= deleted_length
                result.append(entity)
            elif e_start >= position and e_end <= delete_end:
                # Completamente dentro da remoção — remove entidade
                continue
            elif e_start < position and e_end > delete_end:
                # Remoção dentro da entidade
                entity.length -= deleted_length
                result.append(entity)
            elif e_start < position:
                # Remoção remove o final da entidade
                entity.length = position - e_start
                if entity.length > 0:
                    result.append(entity)
            else:
                # Remoção remove o início da entidade
                overlap = delete_end - e_start
                entity.offset = position
                entity.length -= overlap
                if entity.length > 0:
                    result.append(entity)

        return result

    @staticmethod
    def validate_entities(
        text: str,
        entities: list[TypeMessageEntity],
    ) -> list[TypeMessageEntity]:
        """
        Valida e filtra entidades cujos offsets estão fora do texto.
        Remove entidades inválidas.
        """
        text_len = len(text)
        valid = []
        for entity in entities:
            if entity.offset < 0:
                continue
            if entity.offset >= text_len:
                continue
            if entity.offset + entity.length > text_len:
                entity.length = text_len - entity.offset
            if entity.length > 0:
                valid.append(entity)
            else:
                logger.debug("Entidade removida (length=0): %s", type(entity).__name__)
        return valid
