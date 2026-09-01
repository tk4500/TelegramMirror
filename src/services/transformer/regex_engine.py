"""
Engine de substituição de texto via expressões regulares.
Aplica regras de substituição de links e @usernames nas mensagens
antes do re-envio, com suporte a entidades do Telegram.
"""

import re
from telethon.tl.types import (
    MessageEntityTextUrl,
    MessageEntityMention,
    MessageEntityUrl,
    TypeMessageEntity,
)
from src.db.models import ReplacementRule, RuleType
from src.utils.logger import logger

class RegexEngine:
    """
    Aplica substituições configuráveis em texto de mensagens.
    Suporta substituição de links (inclusive text links/entidades ocultas),
    @usernames e padrões regex genéricos.
    Recalcula offsets de entidades após substituições.
    """

    def __init__(self, rules: list[ReplacementRule] | None = None):
        self._rules: list[ReplacementRule] = rules or []

    def set_rules(self, rules: list[ReplacementRule]) -> None:
        """Define as regras de substituição ativas."""
        self._rules = [r for r in rules if r.is_active]
        logger.debug("Regex engine configurada com %d regras ativas.", len(self._rules))

    def apply(
        self,
        text: str,
        entities: list[TypeMessageEntity] | None = None,
    ) -> tuple[str, list[TypeMessageEntity]]:
        """
        Aplica todas as regras de substituição ao texto e entidades.

        Args:
            text: Texto original da mensagem.
            entities: Lista de entidades de formatação (será recalculada).

        Returns:
            Tupla (texto_modificado, entidades_recalculadas).
        """
        if not self._rules or not text:
            return text, entities or []

        entities = list(entities or [])

        for rule in self._rules:
            if rule.rule_type == RuleType.LINK:
                text, entities = self._apply_link_rule(text, entities, rule)
            elif rule.rule_type == RuleType.USERNAME:
                text, entities = self._apply_username_rule(text, entities, rule)
            elif rule.rule_type == RuleType.TEXT:
                text, entities = self._apply_text_rule(text, entities, rule)
            elif rule.rule_type == RuleType.REGEX:
                text, entities = self._apply_regex_rule(text, entities, rule)

        return text, entities

    def _apply_link_rule(
        self, text: str, entities: list[TypeMessageEntity], rule: ReplacementRule
    ) -> tuple[str, list[TypeMessageEntity]]:
        """Substitui links no texto e em entidades TextUrl (links ocultos)."""
        # 1. Substituir em entidades TextUrl (links ocultos)
        for entity in entities:
            if isinstance(entity, MessageEntityTextUrl):
                if rule.old_value in entity.url:
                    entity.url = entity.url.replace(rule.old_value, rule.new_value)

        # 2. Substituir links visíveis no texto
        text, entities = self._replace_in_text(text, entities, rule.old_value, rule.new_value)
        return text, entities

    def _apply_username_rule(
        self, text: str, entities: list[TypeMessageEntity], rule: ReplacementRule
    ) -> tuple[str, list[TypeMessageEntity]]:
        """Substitui @usernames no texto."""
        old_mention = rule.old_value if rule.old_value.startswith("@") else f"@{rule.old_value}"
        new_mention = rule.new_value if rule.new_value.startswith("@") else f"@{rule.new_value}"
        text, entities = self._replace_in_text(text, entities, old_mention, new_mention)
        return text, entities

    def _apply_text_rule(
        self, text: str, entities: list[TypeMessageEntity], rule: ReplacementRule
    ) -> tuple[str, list[TypeMessageEntity]]:
        """Substituição literal de texto."""
        text, entities = self._replace_in_text(text, entities, rule.old_value, rule.new_value)
        return text, entities

    def _apply_regex_rule(
        self, text: str, entities: list[TypeMessageEntity], rule: ReplacementRule
    ) -> tuple[str, list[TypeMessageEntity]]:
        """Substituição usando regex compilado."""
        try:
            pattern = re.compile(rule.old_value)
            # Encontra todos os matches reversos para recalcular offsets
            matches = list(pattern.finditer(text))
            if not matches:
                return text, entities

            # Aplica substituições de trás para frente para manter offsets
            for match in reversed(matches):
                replacement = pattern.sub(rule.new_value, match.group())
                start = match.start()
                end = match.end()
                old_len = end - start
                new_len = len(replacement)
                delta = new_len - old_len

                text = text[:start] + replacement + text[end:]
                entities = self._adjust_offsets(entities, start, old_len, delta)

        except re.error as e:
            logger.error("Regex inválida '%s': %s", rule.old_value, e)
        return text, entities

    def _replace_in_text(
        self,
        text: str,
        entities: list[TypeMessageEntity],
        old: str,
        new: str,
    ) -> tuple[str, list[TypeMessageEntity]]:
        """
        Substitui ocorrências de 'old' por 'new' no texto,
        recalculando offsets das entidades.
        """
        if old not in text:
            return text, entities

        delta = len(new) - len(old)
        offset = 0
        new_text = ""
        last_end = 0

        for match in re.finditer(re.escape(old), text):
            start = match.start()
            end = match.end()
            new_text += text[last_end:start] + new
            entities = self._adjust_offsets(entities, start + offset, len(old), delta)
            offset += delta
            last_end = end

        new_text += text[last_end:]
        return new_text, entities

    @staticmethod
    def _adjust_offsets(
        entities: list[TypeMessageEntity],
        change_pos: int,
        old_len: int,
        delta: int,
    ) -> list[TypeMessageEntity]:
        """
        Recalcula offsets de entidades após uma substituição.

        Args:
            entities: Lista de entidades.
            change_pos: Posição onde a substituição ocorreu.
            old_len: Tamanho do texto original substituído.
            delta: Diferença de tamanho (new_len - old_len).
        """
        adjusted = []
        for entity in entities:
            e_start = entity.offset
            e_end = entity.offset + entity.length

            if e_end <= change_pos:
                # Entidade antes da substituição — não afetada
                adjusted.append(entity)
            elif e_start >= change_pos + old_len:
                # Entidade depois da substituição — desloca offset
                entity.offset += delta
                adjusted.append(entity)
            else:
                # Entidade sobreposta — ajusta tamanho
                if e_start < change_pos:
                    # Substituição dentro da entidade
                    entity.length += delta
                else:
                    # Substituição no início ou engloba a entidade
                    entity.offset += delta
                    entity.length = max(0, entity.length)
                if entity.length > 0:
                    adjusted.append(entity)

        return adjusted
