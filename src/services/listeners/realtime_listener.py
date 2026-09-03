"""
Handler de eventos em tempo real do Telegram.
Escuta novas mensagens no chat de origem e as encaminha/replica
para o destino usando uma fila de processamento assíncrona.
"""

from src.utils.logger import log_execution
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import Message, PeerChannel, PeerUser, PeerChat
from telethon.errors import MessageIdInvalidError

from src.core.config import CopyMode
from src.db.models import ReplacementRule
from src.services.copier.forward_copier import ForwardCopier
from src.services.copier.text_copier import TextCopier
from src.services.copier.album_copier import AlbumCopier
from src.services.copier.text_preprocessor import TextPreprocessor
from src.services.copier.pin_service import PinService
from src.services.transformer.regex_engine import RegexEngine
from src.services.copier.entity_parser import EntityParser
from src.db.models import CopyMode, ReplacementRule
from src.utils.logger import logger, ws_log
import json

class RealtimeListener:
    """
    Listener que monitora novas mensagens em um chat de origem
    e as processa (forward ou replicate) para o chat de destino.
    Usa uma fila assíncrona para processamento ordenado.
    """

    @log_execution
    def __init__(
        self,
        client: TelegramClient,
        source_chat_id: int,
        dest_chat_id: int,
        mode: CopyMode = CopyMode.FORWARD,
        replacement_rules: list[ReplacementRule] | None = None,
        debug_mode: bool = False,
    ):
        self._client = client
        self._source_chat_id = source_chat_id
        self._dest_chat_id = dest_chat_id
        self._mode = mode
        self._debug_mode = debug_mode
        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._is_running = False
        self._worker_task: asyncio.Task | None = None
        self._handler = None

        # Inicializa copiers
        self._forward_copier = ForwardCopier(client)
        self._text_copier = TextCopier(client)
        self._album_copier = AlbumCopier(client)
        self._pin_service = PinService(client)
        self._entity_parser = EntityParser()

        # Regex engine e Preprocessor
        self._regex_engine = RegexEngine(replacement_rules)
        self._text_preprocessor = TextPreprocessor(self._entity_parser, self._regex_engine)

        # Buffer para álbuns (agrupa por grouped_id)
        self._album_buffer: dict[int, list[Message]] = {}
        self._album_timers: dict[int, asyncio.TimerHandle] = {}

        # Callbacks
        self._on_message_processed = None
        self._on_error = None

    @property
    @log_execution
    def is_running(self) -> bool:
        """Retorna True se o listener está ativo."""
        return self._is_running

    @log_execution
    def on_message_processed(self, callback) -> None:
        """Registra callback para quando uma mensagem é processada com sucesso."""
        self._on_message_processed = callback

    @log_execution
    def on_error(self, callback) -> None:
        """Registra callback para erros de processamento."""
        self._on_error = callback

    @log_execution
    async def start(self) -> None:
        """Inicia o listener e o worker de processamento."""
        if self._is_running:
            logger.warning("Listener já está ativo.")
            return

        self._is_running = True

        # Registra handler de novos eventos
        @self._client.on(events.NewMessage(chats=self._source_chat_id))
        @log_execution
        async def handler(event):
            if self._is_running:
                await self._queue.put(event.message)

        self._handler = handler

        # Inicia worker de processamento
        self._worker_task = asyncio.create_task(self._process_queue())

        logger.info(
            "Listener iniciado: %d -> %d (modo: %s)",
            self._source_chat_id, self._dest_chat_id, self._mode.value,
        )

    @log_execution
    async def stop(self) -> None:
        """
        Para o listener de forma segura.
        Aguarda a mensagem atual ser processada antes de encerrar.
        """
        if not self._is_running:
            return

        self._is_running = False

        # Remove handler de eventos
        if self._handler:
            self._client.remove_event_handler(self._handler)
            self._handler = None

        # Aguarda a fila esvaziar (processa o que já entrou)
        if not self._queue.empty():
            logger.info("Aguardando %d mensagens na fila serem processadas...", self._queue.qsize())
            await self._queue.join()

        # Cancela o worker
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        logger.info("Listener parado: %d -> %d", self._source_chat_id, self._dest_chat_id)

    @log_execution
    async def pause(self) -> None:
        """Pausa o listener (para de aceitar novas mensagens, mas processa a atual)."""
        self._is_running = False
        if self._handler:
            self._client.remove_event_handler(self._handler)
            self._handler = None
        logger.info("Listener pausado.")

    @log_execution
    async def _process_queue(self) -> None:
        """Worker que processa mensagens da fila uma por uma."""
        while True:
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if not self._is_running and self._queue.empty():
                    break
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._process_message(message)
                self._queue.task_done()
            except Exception as e:
                logger.error("Erro ao processar mensagem %d: %s", message.id, e)
                self._queue.task_done()
                if self._on_error:
                    await self._on_error(message, e)

    @log_execution
    async def _process_message(self, message: Message) -> None:
        """Processa uma única mensagem (forward ou replicate)."""
        # Verifica se faz parte de um álbum
        if self._album_copier.is_album_message(message):
            await self._handle_album_message(message)
            return

        if self._debug_mode:
            try:
                await ws_log(f"Debug [Original Realtime] Mensagem {message.id}", "INFO", {"original": message.to_dict()})
            except Exception as e:
                pass

        sent_message = None

        if self._mode == CopyMode.FORWARD:
            sent_message = await self._forward_copier.forward_message(
                self._source_chat_id, self._dest_chat_id, message.id
            )
        elif self._mode == CopyMode.REPLICATE:
            parsed, transformations = self._text_preprocessor._process_text(message)

            if self._debug_mode and transformations:
                try:
                    await ws_log(f"Debug [Transformação] Mensagem {message.id}", "INFO", transformations)
                except Exception:
                    pass

            # Copia com base no tipo de mídia
            if parsed.has_media:
                # IMPORTANTE: Em Realtime, não temos o preloader rodando, 
                # então ele baixará na hora (utilizando as otimizações FastTelethon que implementaremos no copier)
                sent_message = await self._text_copier.replicate_message(
                    self._dest_chat_id, message, parsed_override=parsed, preloader=None
                )
            elif parsed.text:
                sent_message = await self._client.send_message(
                    entity=self._dest_chat_id,
                    message=parsed.text,
                    formatting_entities=parsed.entities,
                    parse_mode=None,
                    link_preview=False,
                )

        # Sincroniza pin se necessário
        if sent_message and self._pin_service.is_pinned(message):
            await self._pin_service.pin_message(self._dest_chat_id, sent_message.id)

        # Callback de sucesso
        if sent_message and self._on_message_processed:
            await self._on_message_processed(message, sent_message)

    @log_execution
    async def _handle_album_message(self, message: Message) -> None:
        """
        Bufferiza mensagens de álbum e processa quando completo.
        Aguarda 2 segundos após a última mensagem do grupo para
        garantir que todas as partes chegaram.
        """
        group_id = message.grouped_id

        if group_id not in self._album_buffer:
            self._album_buffer[group_id] = []

        self._album_buffer[group_id].append(message)

        # Cancela timer anterior se existir
        if group_id in self._album_timers:
            self._album_timers[group_id].cancel()

        # Programa processamento após 2s de silêncio
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            2.0,
            lambda gid=group_id: asyncio.create_task(self._flush_album(gid))
        )
        self._album_timers[group_id] = timer

    @log_execution
    async def _flush_album(self, group_id: int) -> None:
        """Processa um álbum completo bufferizado."""
        album_messages = self._album_buffer.pop(group_id, [])
        self._album_timers.pop(group_id, None)

        if not album_messages:
            return

        album_messages.sort(key=lambda m: m.id)

        try:
            if self._mode == CopyMode.FORWARD:
                await self._album_copier.forward_album(
                    self._source_chat_id, self._dest_chat_id, album_messages
                )
            else:
                await self._album_copier.replicate_album(
                    self._dest_chat_id, album_messages
                )
            logger.info("Álbum %d processado (%d itens).", group_id, len(album_messages))
        except Exception as e:
            logger.error("Erro ao processar álbum %d: %s", group_id, e)