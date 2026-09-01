"""
Motor de cópia histórica (backfill) do Telegram.
Itera pelo histórico de mensagens do chat de origem e as copia
para o destino, com controle de lote, delay anti-flood e checkpoints.
"""

from src.utils.logger import log_execution
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
from src.services.copier.forward_copier import ForwardCopier
from src.services.copier.text_copier import TextCopier
from src.services.copier.album_copier import AlbumCopier
from src.services.copier.pin_service import PinService
from src.services.transformer.regex_engine import RegexEngine
from src.services.copier.entity_parser import EntityParser
from src.db.models import CopyMode, SpeedProfile, ReplacementRule
from src.utils.logger import logger, ws_log
import json

# Delays por perfil de velocidade (em segundos)
SPEED_DELAYS = {
    SpeedProfile.SAFE: {"message": 3.0, "batch_pause": 30.0, "batch_size": 10},
    SpeedProfile.MODERATE: {"message": 1.5, "batch_pause": 15.0, "batch_size": 25},
    SpeedProfile.FAST: {"message": 0.3, "batch_pause": 5.0, "batch_size": 50},
}

class HistoryBackfill:
    """
    Motor de cópia retroativa de histórico de mensagens.
    Suporta retomada a partir de checkpoint (last_message_id),
    perfis de velocidade e tratamento de FloodWait.
    """

    @log_execution
    def __init__(
        self,
        client: TelegramClient,
        source_chat_id: int,
        dest_chat_id: int,
        mode: CopyMode = CopyMode.FORWARD,
        speed_profile: SpeedProfile = SpeedProfile.SAFE,
        replacement_rules: list[ReplacementRule] | None = None,
        debug_mode: bool = False,
        preserve_custom_emojis: bool = False,
    ):
        self._client = client
        self._source_chat_id = source_chat_id
        self._dest_chat_id = dest_chat_id
        self._mode = mode
        self._speed = SPEED_DELAYS[speed_profile]
        self._debug_mode = debug_mode
        self._preserve_custom_emojis = preserve_custom_emojis

        # Copiers
        self._forward_copier = ForwardCopier(client)
        self._text_copier = TextCopier(client, preserve_custom_emojis=self._preserve_custom_emojis)
        self._album_copier = AlbumCopier(client)
        self._pin_service = PinService(client)
        self._entity_parser = EntityParser()
        self._regex_engine = RegexEngine(replacement_rules)

        # Estado
        self._is_running = False
        self._is_paused = False
        self._processed_count = 0
        self._failed_count = 0
        self._last_message_id = 0

        # Callbacks
        self._on_progress = None
        self._on_message_processed = None
        self._on_error = None

    @property
    @log_execution
    def is_running(self) -> bool:
        return self._is_running

    @property
    @log_execution
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    @log_execution
    def processed_count(self) -> int:
        return self._processed_count

    @property
    @log_execution
    def failed_count(self) -> int:
        return self._failed_count

    @property
    @log_execution
    def last_message_id(self) -> int:
        return self._last_message_id

    @log_execution
    def on_progress(self, callback) -> None:
        """Registra callback de progresso (chamado a cada mensagem)."""
        self._on_progress = callback

    @log_execution
    def on_message_processed(self, callback) -> None:
        """Registra callback para mensagem processada com sucesso."""
        self._on_message_processed = callback

    @log_execution
    def on_error(self, callback) -> None:
        """Registra callback para erros."""
        self._on_error = callback

    @log_execution
    async def start(
        self,
        start_from_id: int = 0,
        total_limit: int | None = None,
    ) -> dict:
        """
        Inicia a cópia do histórico de forma contínua.
        """
        self._is_running = True
        self._is_paused = False
        self._processed_count = 0
        self._failed_count = 0
        self._last_message_id = start_from_id

        logger.info(
            "Backfill iniciado: %d -> %d (modo: %s, a partir de: %d)",
            self._source_chat_id, self._dest_chat_id,
            self._mode.value, start_from_id,
        )

        batch_count = 0
        album_buffer: dict[int, list[Message]] = {}

        try:
            async for message in self._client.iter_messages(
                self._source_chat_id,
                min_id=start_from_id,
                reverse=True,
                limit=total_limit,
            ):
                if not await self._loop_core(message, album_buffer, batch_count):
                    break
                batch_count += 1

            # Processa álbuns restantes
            await self._flush_pending_albums(album_buffer, force_all=True)

        except FloodWaitError as e:
            logger.warning("FloodWait durante backfill: aguardando %ds.", e.seconds)
            await asyncio.sleep(e.seconds)
            if self._is_running:
                return await self.start(
                    start_from_id=self._last_message_id,
                    total_limit=total_limit - self._processed_count if total_limit else None,
                )
        except Exception as e:
            logger.error("Erro durante backfill: %s", e)
            if self._on_error:
                await self._on_error(None, e)
        finally:
            self._is_running = False

        result = {
            "processed": self._processed_count,
            "failed": self._failed_count,
            "last_message_id": self._last_message_id,
            "status": "completed" if not self._is_paused else "paused",
        }
        logger.info("Backfill finalizado: %s", result)
        return result

    @log_execution
    async def start_selective(self, message_ids: list[int]) -> dict:
        """
        Inicia a cópia apenas para uma lista específica de mensagens.
        """
        self._is_running = True
        self._is_paused = False
        self._processed_count = 0
        self._failed_count = 0

        logger.info(
            "Cópia seletiva iniciada: %d -> %d (%d mensagens)",
            self._source_chat_id, self._dest_chat_id, len(message_ids)
        )

        batch_count = 0
        album_buffer: dict[int, list[Message]] = {}

        # Ordena para garantir que a extração ocorra de baixo para cima (cronológica)
        message_ids.sort()

        try:
            for chunk in [message_ids[i:i+50] for i in range(0, len(message_ids), 50)]:
                # Baixa do Telegram as mensagens exatas requisitadas via get_messages
                messages = await self._client.get_messages(self._source_chat_id, ids=chunk)
                # get_messages pode retornar None para IDs inválidos, filtre-os
                messages = [m for m in messages if m is not None]

                for message in messages:
                    if not await self._loop_core(message, album_buffer, batch_count):
                        break
                    batch_count += 1

                if not self._is_running:
                    break

            await self._flush_pending_albums(album_buffer, force_all=True)

        except Exception as e:
            logger.error("Erro durante cópia seletiva: %s", e)
            if self._on_error:
                await self._on_error(None, e)
        finally:
            self._is_running = False

        return {
            "processed": self._processed_count,
            "failed": self._failed_count,
            "last_message_id": self._last_message_id,
            "status": "completed" if not self._is_paused else "paused",
        }

    @log_execution
    async def _loop_core(self, message: Message, album_buffer: dict, batch_count: int) -> bool:
        """Core loop handling para cada mensagem lida."""
        # Verifica pausa/stop
        while self._is_paused:
            await asyncio.sleep(0.5)
        if not self._is_running:
            logger.info("Backfill interrompido pelo usuário.")
            return False

        # Bufferiza mensagens de álbum
        if message.grouped_id is not None:
            gid = message.grouped_id
            if gid not in album_buffer:
                album_buffer[gid] = []
            album_buffer[gid].append(message)
            return True

        # Processa álbuns pendentes cujo grupo já passou
        await self._flush_pending_albums(album_buffer)

        # Processa mensagem individual
        success = await self._process_single_message(message)

        # Se success for None, significa que foi ignorada (vazia/apagada)
        if success is True:
            logger.info("MENSAGEM ORIGINAL ID %d -> COPIADA COM SUCESSO. (Lote atual: %d)", message.id, batch_count)
            self._processed_count += 1
        elif success is False:
            logger.error("MENSAGEM ORIGINAL ID %d -> FALHA AO COPIAR. (Lote atual: %d)", message.id, batch_count)
            self._failed_count += 1
        else:
            logger.debug("MENSAGEM ORIGINAL ID %d -> IGNORADA. (Lote atual: %d)", message.id, batch_count)

        self._last_message_id = message.id

        # Delay anti-flood
        await asyncio.sleep(self._speed["message"])

        # Pausa entre lotes
        if batch_count > 0 and batch_count % self._speed["batch_size"] == 0:
            logger.debug("Pausa de lote: %.1fs", self._speed["batch_pause"])
            await asyncio.sleep(self._speed["batch_pause"])

        # Callback de progresso
        if self._on_progress:
            await self._on_progress(
                self._processed_count, self._failed_count, self._last_message_id
            )

        return True

    @log_execution
    async def stop(self) -> None:
        """Para o backfill (aguarda mensagem atual terminar)."""
        self._is_running = False
        logger.info("Backfill parando...")

    @log_execution
    async def pause(self) -> None:
        """Pausa o backfill."""
        self._is_paused = True
        logger.info("Backfill pausado.")

    @log_execution
    async def resume(self) -> None:
        """Retoma o backfill pausado."""
        self._is_paused = False
        logger.info("Backfill retomado.")

    @log_execution
    async def _process_single_message(self, message: Message) -> bool | None:
        """Processa uma única mensagem. Retorna True se sucesso, None se ignorada/apagada."""
        try:
            # 6.1 Validação de Integridade: Ignorar mensagens vazias (sem texto e sem mídia)
            # Geralmente também identifica mensagens que foram deletadas (mensagem de sistema vazia)
            if getattr(message, 'deleted', False) or (not message.text and not message.media and not getattr(message, 'action', None)):
                logger.debug("Mensagem %d ignorada (vazia ou apagada da origem).", message.id)
                # Retorna None para sinalizar que foi ignorada legitimamente, não conta como falha
                return None

            if self._debug_mode:
                try:
                    await ws_log(f"Debug [Original] Mensagem {message.id}", "INFO", {"original": message.to_dict()})
                except Exception as e:
                    pass

            sent = None

            if self._mode == CopyMode.FORWARD:
                sent = await self._forward_copier.forward_message(
                    self._source_chat_id, self._dest_chat_id, message.id
                )
            elif self._mode == CopyMode.REPLICATE:
                parsed = self._entity_parser.parse_message(message)

                # Strip custom emojis directly so Telethon doesn't throw a Premium error
                # Guardamos o total original para o debug_mode
                orig_entities_count = len(parsed.entities)
                parsed.entities = self._entity_parser.clone_entities(parsed.entities, preserve_custom_emojis=self._preserve_custom_emojis)
                dropped_emojis = orig_entities_count - len(parsed.entities)

                transformations = {}
                if dropped_emojis > 0:
                    transformations["dropped_custom_emojis"] = dropped_emojis

                if self._regex_engine._rules:
                    orig_text = parsed.text
                    parsed.text, parsed.entities = self._regex_engine.apply(
                        parsed.text, parsed.entities
                    )
                    if orig_text != parsed.text:
                        transformations["regex_text_changed"] = {"from": orig_text, "to": parsed.text}

                if self._debug_mode and transformations:
                    await ws_log(f"Debug [Transformação] Mensagem {message.id}", "INFO", transformations)

                if parsed.has_media:
                    # Modify text copier logic inline safely via custom method
                    sent = await self._text_copier.replicate_message(
                        self._dest_chat_id, message, parsed_override=parsed
                    )
                elif parsed.text:
                    sent = await self._client.send_message(
                        entity=self._dest_chat_id,
                        message=parsed.text,
                        formatting_entities=parsed.entities,
                        link_preview=False,
                    )

            # Sincroniza pin
            if sent and self._pin_service.is_pinned(message):
                await self._pin_service.pin_message(self._dest_chat_id, sent.id)

            if sent and self._on_message_processed:
                await self._on_message_processed(message, sent)

            if sent:
                logger.info(f"Mensagem {message.id} enviada com sucesso no chat de destino {self._dest_chat_id}.")
            return sent is not None

        except FloodWaitError:
            raise
        except Exception as e:
            # Em mensagens premium ou contendo mídia proprietária da rede de teste/prod, a exceção pode ser vaga.
            # Convertendo detalhes aprimorados para os logs.
            error_details = str(e)
            if "MessageEntityCustomEmoji" in error_details or "PREMIUM" in error_details.upper() or "WEBPAGE_CURL_FAILED" in error_details:
                error_details = f"Recurso Premium ou Formatação Customizada bloqueada pelo Telegram. Mensagem original: {error_details}"
            elif "PROTECTED" in error_details.upper() or "You can't forward messages from a protected chat" in error_details:
                error_details = f"O Chat tem proteção contra Encaminhamento ativada. Use o modo Replicar. Detalhes: {error_details}"

            logger.error("Falha ao processar mensagem %d: %s", message.id, error_details)

            # Quando um erro ocorrer, se on_error estiver registrado, passar para salvar no DB de falhas
            if self._on_error:
                # Modificando Exception para garantir mensagem mais limpa pro frontend (ver api_orchestrator)
                await self._on_error(message, Exception(error_details))
            return False

    @log_execution
    async def _flush_pending_albums(
        self,
        album_buffer: dict[int, list[Message]],
        force_all: bool = False,
    ) -> None:
        """Processa álbuns completos do buffer."""
        if force_all:
            group_ids = list(album_buffer.keys())
        else:
            # Processa apenas álbuns com 2+ mensagens e sem novas adições recentes
            group_ids = [gid for gid, msgs in album_buffer.items() if len(msgs) >= 2]

        for gid in group_ids:
            messages = album_buffer.pop(gid, [])
            if not messages:
                continue
            messages.sort(key=lambda m: m.id)

            try:
                if self._mode == CopyMode.FORWARD:
                    await self._album_copier.forward_album(
                        self._source_chat_id, self._dest_chat_id, messages
                    )
                else:
                    await self._album_copier.replicate_album(
                        self._dest_chat_id, messages
                    )
                self._processed_count += len(messages)
                self._last_message_id = messages[-1].id
            except Exception as e:
                logger.error("Erro ao processar álbum %d: %s", gid, e)
                self._failed_count += len(messages)
