"""
Preloader de mídias assíncrono.
Antecipa o download e upload das mídias das mensagens para agilizar a cópia.
"""

import asyncio
import os
import time
import psutil
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
from src.utils.logger import logger, ws_log
from src.utils.disk_monitor import DiskMonitor
from src.utils.fast_telethon import download_file, upload_file

class MediaPreloader:
    def __init__(self, client: TelegramClient, max_workers: int = 100, **kwargs):
        self._client = client
        self._queue = asyncio.Queue()
        self._results = {}
        self._events = {}
        self._max_workers = max_workers
        self._active_workers = 2 # Start with 2, adjusts dynamically
        self._workers = []
        self._monitor_task = None
        self._disk_monitor = DiskMonitor()
        self._download_only = kwargs.get('download_only', False)
        if self._download_only:
            self._download_dir = Path("data/downloads")
            self._download_dir.mkdir(parents=True, exist_ok=True)
        
    async def start(self):
        """Inicia os workers e o monitoramento."""
        for i in range(self._max_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        self._monitor_task = asyncio.create_task(self._monitor_resources())
        
    async def stop(self):
        """Para os workers e o monitoramento."""
        if self._monitor_task:
            self._monitor_task.cancel()
        for task in self._workers:
            task.cancel()
            
    def enqueue(self, message: Message):
        """Coloca a mensagem na fila para pré-carregamento, se tiver mídia."""
        if not getattr(message, 'media', None):
            return
        # Inicializa o Event para quem for aguardar por essa mensagem
        if message.id not in self._events:
            self._events[message.id] = asyncio.Event()
        self._queue.put_nowait(message)
        
    async def get_preloaded(self, msg_id: int):
        """
        Retorna o InputFile já feito o upload (ou aguarda ficar pronto).
        Retorna None se houve erro no processo ou se não foi precarregado.
        """
        if msg_id not in self._events:
            return None
            
        event = self._events[msg_id]
        if not event.is_set():
            logger.info("Aguardando o preloader finalizar a mensagem %d...", msg_id)
            await event.wait()
            
        return self._results.get(msg_id)

    async def _monitor_resources(self):
        """Monitora recursos e ajusta o número de workers simultâneos."""
        while True:
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                is_disk_critical = self._disk_monitor.is_space_critical()
                
                if cpu > 95 or ram > 90 or is_disk_critical:
                    # Reduz workers se sobrecarregado
                    self._active_workers = max(1, self._active_workers - 1)
                elif cpu < 60 and ram < 80 and not is_disk_critical:
                    # Aumenta workers se folgado
                    self._active_workers = min(self._max_workers, self._active_workers + 1)
                
                await asyncio.sleep(2)
            except Exception as e:
                logger.error("Erro no monitor do preloader: %s", e)
                await asyncio.sleep(5)
                
    async def _worker(self, worker_id: int):
        """Trabalhador que processa o download/upload de uma mensagem."""
        while True:
            # Pausa o worker se estiver além do limite ativo
            if worker_id >= self._active_workers:
                await asyncio.sleep(1)
                continue
                
            try:
                msg = await self._queue.get()
            except asyncio.CancelledError:
                break
                
            try:
                await self._process_message(msg)
            except Exception as e:
                logger.error("Worker %d erro na msg %d: %s", worker_id, msg.id, e)
                self._results[msg.id] = None
                if msg.id in self._events:
                    self._events[msg.id].set()
            finally:
                self._queue.task_done()
                
    async def _process_message(self, msg: Message):
        try:
            # Refaz o fetch da mensagem para renovar o file_reference (evita erro de expiração)
            try:
                if msg.chat_id:
                    fresh_msg = await self._client.get_messages(msg.chat_id, ids=msg.id)
                    if fresh_msg and getattr(fresh_msg, 'media', None):
                        msg = fresh_msg
            except Exception as e:
                logger.warning("Não foi possível refazer o fetch da msg %d no preloader: %s", msg.id, e)

            msg_info = f"Preloader: Iniciando download/upload da msg ID {msg.id}"
            logger.info(msg_info)
            await ws_log(msg_info, "INFO")
            
            # Download
            last_log = time.time()
            async def progress_dl(current, total):
                nonlocal last_log
                now = time.time()
                if now - last_log > 5:
                    percent = (current / total) * 100 if total else 0
                    prog = f"Preloader DL (Msg {msg.id}): {percent:.1f}% ({current}/{total})"
                    logger.info(prog)
                    await ws_log(prog, "INFO")
                    last_log = now
                    
            ext = getattr(msg.file, "ext", "")
            file_name = getattr(msg.file, "name", "")
            if not file_name:
                file_name = f"media_{msg.id}{ext}"
            
            if self._download_only:
                chat_dir = self._download_dir / str(msg.chat_id)
                chat_dir.mkdir(exist_ok=True)
                media_path = str(chat_dir / file_name)
                # Ensure filename uniqueness if it already exists
                if os.path.exists(media_path):
                    media_path = str(chat_dir / f"{msg.id}_{file_name}")
            else:
                media_path = f"data/temp/{msg.id}_{int(time.time())}{ext}"
            
            with open(media_path, "wb") as f:
                file_size = getattr(msg.file, "size", 0)
                await download_file(self._client, msg.media, f, progress_callback=progress_dl, size=file_size)
            
            if not os.path.exists(media_path) or os.path.getsize(media_path) == 0:
                self._results[msg.id] = None
                if msg.id in self._events:
                    self._events[msg.id].set()
                return
                
            if self._download_only:
                self._results[msg.id] = media_path
                succ = f"Preloader: Download da msg {msg.id} concluído para {media_path}."
                logger.info(succ)
                await ws_log(succ, "OK")
                return

            # Upload
            last_log = time.time()
            async def progress_ul(current, total):
                nonlocal last_log
                now = time.time()
                if now - last_log > 5:
                    percent = (current / total) * 100 if total else 0
                    prog = f"Preloader UP (Msg {msg.id}): {percent:.1f}% ({current}/{total})"
                    logger.info(prog)
                    await ws_log(prog, "INFO")
                    last_log = now
                    
            with open(media_path, "rb") as f:
                input_file = await upload_file(self._client, f, progress_callback=progress_ul)
                input_file.name = file_name
            
            # Limpeza local
            try:
                os.remove(media_path)
            except Exception:
                pass
                
            self._results[msg.id] = input_file
            
            succ = f"Preloader: Upload da msg {msg.id} concluído com sucesso e pronto para uso."
            logger.info(succ)
            await ws_log(succ, "OK")
            
        except FloodWaitError as e:
            logger.warning("Preloader FloodWait (%ds) na msg %d", e.seconds, msg.id)
            await asyncio.sleep(e.seconds)
            await self._process_message(msg) # tenta de novo
        except Exception as e:
            logger.error("Preloader falhou na msg %d: %s", msg.id, e)
            self._results[msg.id] = None
        finally:
            if msg.id in self._events:
                self._events[msg.id].set()
