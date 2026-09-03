"""
Text Preprocessor Assíncrono.
Pré-processa as mensagens extraindo entidades e aplicando regexes
em paralelo usando workers.
"""

import asyncio
from telethon.tl.types import Message
from src.services.copier.entity_parser import EntityParser, ParsedMessage
from src.services.transformer.regex_engine import RegexEngine
from src.utils.logger import logger

class TextPreprocessor:
    def __init__(self, parser: EntityParser, regex_engine: RegexEngine, max_workers: int = 10):
        self._parser = parser
        self._regex_engine = regex_engine
        self._queue = asyncio.Queue()
        self._results = {}
        self._events = {}
        self._max_workers = max_workers
        self._workers = []

    async def start(self):
        """Inicia os workers."""
        for i in range(self._max_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)

    async def stop(self):
        """Para os workers."""
        for task in self._workers:
            task.cancel()

    def enqueue(self, message: Message):
        """Coloca a mensagem na fila para pré-processamento."""
        if message.id not in self._events:
            self._events[message.id] = asyncio.Event()
        self._queue.put_nowait(message)

    async def get_prepared(self, msg_id: int) -> tuple[ParsedMessage, dict]:
        """
        Retorna (ParsedMessage, transformations) pré-processados (ou aguarda).
        """
        if msg_id not in self._events:
            return None, {}

        event = self._events[msg_id]
        if not event.is_set():
            await event.wait()

        return self._results.get(msg_id, (None, {}))

    async def _worker(self, worker_id: int):
        """Worker que consome a fila de mensagens e faz o parser e regex."""
        while True:
            try:
                msg = await self._queue.get()
            except asyncio.CancelledError:
                break
            
            try:
                parsed, transformations = self._process_text(msg)
                self._results[msg.id] = (parsed, transformations)
            except Exception as e:
                logger.error("TextPreprocessor Worker %d erro na msg %d: %s", worker_id, msg.id, e)
                self._results[msg.id] = (None, {})
            finally:
                self._events[msg.id].set()
                self._queue.task_done()

    def _process_text(self, message: Message) -> tuple[ParsedMessage, dict]:
        """
        Lógica pura de CPU: parser, clonagem de entidades e aplicação de regex.
        """
        parsed = self._parser.parse_message(message)
        
        orig_entities_count = len(parsed.entities)
        cloned_entities = self._parser.clone_entities(parsed.entities)
        dropped_emojis = orig_entities_count - len(cloned_entities)
        parsed.entities = cloned_entities

        transformations = {}
        if dropped_emojis > 0:
            transformations["dropped_custom_emojis"] = dropped_emojis

        # Aplica substituições se configuradas
        if self._regex_engine and self._regex_engine._rules:
            orig_text = parsed.text
            parsed.text, parsed.entities = self._regex_engine.apply(
                parsed.text, parsed.entities
            )
            if orig_text != parsed.text:
                transformations["regex_text_changed"] = {"from": orig_text, "to": parsed.text}
        
        return parsed, transformations
