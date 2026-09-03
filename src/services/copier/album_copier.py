"""
Replicador de álbuns (mídias agrupadas) do Telegram.
Agrupa mensagens pelo grouped_id e reenvia como álbum unificado,
preservando ordem, legendas e entidades de formatação.
"""

from src.utils.logger import log_execution
from telethon import TelegramClient
from telethon.tl.types import Message, InputMediaUploadedPhoto, InputMediaUploadedDocument
from telethon.errors import FloodWaitError
import asyncio
import os
import time
from src.services.copier.entity_parser import EntityParser
from src.utils.logger import logger, ws_log

class AlbumCopier:
    """
    Copia álbuns (mídias agrupadas por grouped_id) do Telegram.
    Mantém a ordem original, legendas por item e formatação de entidades.
    """

    @log_execution
    def __init__(self, client: TelegramClient):
        self._client = client
        self._parser = EntityParser()

    @staticmethod
    @log_execution
    def group_messages_by_album(messages: list[Message]) -> dict[int, list[Message]]:
        """
        Agrupa mensagens por grouped_id.
        Mensagens sem grouped_id são ignoradas.

        Args:
            messages: Lista de mensagens a agrupar.

        Returns:
            Dicionário grouped_id -> lista de mensagens (ordenadas por ID).
        """
        albums: dict[int, list[Message]] = {}
        for msg in messages:
            if msg.grouped_id is not None:
                if msg.grouped_id not in albums:
                    albums[msg.grouped_id] = []
                albums[msg.grouped_id].append(msg)

        # Ordena cada álbum por message ID (preserva ordem original)
        for group_id in albums:
            albums[group_id].sort(key=lambda m: m.id)

        return albums

    @staticmethod
    @log_execution
    def is_album_message(message: Message) -> bool:
        """Verifica se uma mensagem faz parte de um álbum."""
        return message.grouped_id is not None

    @log_execution
    async def replicate_album(
        self,
        dest_chat_id: int,
        album_messages: list[Message],
        preloader=None
    ) -> list[Message] | None:
        """
        Copia um álbum inteiro para o destino (modo Replicar).
        Se preloader for fornecido, aguarda e obtém os InputFiles pré-carregados.ixa todas as mídias, preserva legendas/entidades e reenvia como grupo.

        Args:
            dest_chat_id: ID do chat de destino.
            album_messages: Lista de mensagens do álbum (ordenadas por ID).

        Returns:
            Lista de mensagens enviadas, ou None se falhou.
        """
        if not album_messages:
            return None

        media_files: list[str] = []
        captions: list[str] = []
        caption_entities: list[list] = []
        total_items = len(album_messages)
        group_id = album_messages[0].grouped_id

        msg_info = f"Processando álbum (Grupo ID: {group_id}) com {total_items} itens..."
        logger.info(msg_info)
        await ws_log(msg_info, "INFO")

        try:
            for i, msg in enumerate(album_messages, start=1):
                if preloader:
                    input_file = await preloader.get_preloaded(msg.id)
                    if input_file is None:
                        warn_msg = f"Não foi possível obter mídia do preloader para o item {msg.id} do álbum."
                        logger.warning(warn_msg)
                        await ws_log(warn_msg, "WARN")
                        media_files.append("")
                    else:
                        media_files.append(input_file)
                else:
                    msg_down = f"Baixando arquivo {i}/{total_items} do álbum (Mensagem ID: {msg.id})..."
                    logger.info(msg_down)
                    await ws_log(msg_down, "INFO")
                    
                    last_download_log = time.time()
                    async def download_progress(current, total):
                        nonlocal last_download_log
                        now = time.time()
                        if now - last_download_log > 5:
                            percent = (current / total) * 100 if total else 0
                            prog_msg = f"Progresso do download do álbum ({i}/{total_items}): {percent:.1f}% ({current}/{total} bytes)"
                            logger.info(prog_msg)
                            await ws_log(prog_msg, "INFO")
                            last_download_log = now

                    media_path = await self._client.download_media(msg, file="data/temp/", progress_callback=download_progress)
                    if media_path is None:
                        warn_msg = f"Não foi possível baixar mídia do item {msg.id} do álbum."
                        logger.warning(warn_msg)
                        await ws_log(warn_msg, "WARN")
                        media_files.append("")
                    else:
                        succ_msg = f"Arquivo {i}/{total_items} baixado com sucesso."
                        logger.info(succ_msg)
                        await ws_log(succ_msg, "OK")
                        media_files.append(media_path)

                # Captura legenda e entidades de cada item
                parsed = self._parser.parse_message(msg)
                captions.append(parsed.text)
                caption_entities.append(self._parser.clone_entities(parsed.entities))

            # Filtra itens sem mídia
            valid_items = [
                (f, c, e) for f, c, e in zip(media_files, captions, caption_entities)
                if f
            ]

            if not valid_items:
                logger.error("Nenhuma mídia válida no álbum. Pulando.")
                return None

            files = [item[0] for item in valid_items]
            caps = [item[1] for item in valid_items]
            ents = [item[2] for item in valid_items]

            end_down_msg = f"Mídias preparadas. Iniciando o envio para o destino {dest_chat_id}..."
            logger.info(end_down_msg)
            await ws_log(end_down_msg, "INFO")

            last_upload_log = time.time()
            async def upload_progress(current, total):
                nonlocal last_upload_log
                now = time.time()
                if now - last_upload_log > 5:
                    if isinstance(current, float):
                        prog_msg = f"Progresso do envio do álbum: {current:.1f} / {total} arquivos"
                    else:
                        percent = (current / total) * 100 if total else 0
                        prog_msg = f"Progresso do envio do álbum: {percent:.1f}% ({current}/{total} bytes)"
                    logger.info(prog_msg)
                    await ws_log(prog_msg, "INFO")
                    last_upload_log = now

            # Envia como álbum — Telethon send_file com lista de arquivos
            # A legenda vai apenas no primeiro item (padrão Telegram)
            # Para preservar legendas individuais, enviamos com caption por item
            sent_messages = await self._client.send_file(
                entity=dest_chat_id,
                file=files,
                caption=caps,
                formatting_entities=ents[0] if ents else None,
                parse_mode=None,
                progress_callback=upload_progress if not preloader else None,
            )

            if not isinstance(sent_messages, list):
                sent_messages = [sent_messages]

            succ_msg = f"Álbum replicado com sucesso! {len(sent_messages)} itens enviados para {dest_chat_id}."
            logger.info(succ_msg)
            await ws_log(succ_msg, "OK")
            return sent_messages

        except FloodWaitError:
            raise
        except Exception as e:
            logger.error("Erro ao replicar álbum para %d: %s", dest_chat_id, e)
            return None
        finally:
            # Limpa arquivos temporários apenas se não usamos preloader
            # (O preloader limpa os próprios arquivos temporários)
            if not preloader:
                for mf in media_files:
                    if mf and os.path.exists(mf):
                        try:
                            os.remove(mf)
                        except OSError:
                            pass

    @log_execution
    async def forward_album(
        self,
        source_chat_id: int,
        dest_chat_id: int,
        album_messages: list[Message],
    ) -> list[Message] | None:
        """
        Encaminha um álbum usando forward nativo (preserva 'Encaminhado de...').

        Args:
            source_chat_id: ID do chat de origem.
            dest_chat_id: ID do chat de destino.
            album_messages: Mensagens do álbum.

        Returns:
            Lista de mensagens encaminhadas ou None.
        """
        if not album_messages:
            return None

        total_items = len(album_messages)
        group_id = album_messages[0].grouped_id
        msg_info = f"Processando encaminhamento de álbum (Grupo ID: {group_id}) com {total_items} itens. Encaminhando de {source_chat_id} para {dest_chat_id}..."
        logger.info(msg_info)
        await ws_log(msg_info, "INFO")

        try:
            message_ids = [msg.id for msg in album_messages]
            result = await self._client.forward_messages(
                entity=dest_chat_id,
                messages=message_ids,
                from_peer=source_chat_id,
            )
            if not isinstance(result, list):
                result = [result]
            
            succ_msg = f"Álbum encaminhado com sucesso! {len(result)} itens enviados para {dest_chat_id}."
            logger.info(succ_msg)
            await ws_log(succ_msg, "OK")
            
            return result
        except FloodWaitError:
            raise
        except Exception as e:
            logger.error("Erro ao encaminhar álbum: %s", e)
            return None
