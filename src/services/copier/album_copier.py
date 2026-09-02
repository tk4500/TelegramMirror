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
from src.utils.logger import logger

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
    ) -> list[Message] | None:
        """
        Replica um álbum completo no destino.
        Baixa todas as mídias, preserva legendas/entidades e reenvia como grupo.

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

        logger.info("Processando álbum (Grupo ID: %s) com %d itens. Iniciando download das mídias...", group_id, total_items)

        try:
            # Baixa todas as mídias do álbum
            for i, msg in enumerate(album_messages, start=1):
                logger.info("Baixando arquivo %d/%d do álbum (Mensagem ID: %d)...", i, total_items, msg.id)
                
                last_download_log = time.time()
                async def download_progress(current, total):
                    nonlocal last_download_log
                    now = time.time()
                    if now - last_download_log > 5:
                        percent = (current / total) * 100 if total else 0
                        logger.info("Progresso do download do álbum (%d/%d): %.1f%% (%d/%d bytes)", i, total_items, percent, current, total)
                        last_download_log = now

                media_path = await self._client.download_media(msg, file="data/temp/", progress_callback=download_progress)
                if media_path is None:
                    logger.warning("Não foi possível baixar mídia do item %d do álbum.", msg.id)
                    media_files.append("")
                else:
                    logger.info("Arquivo %d/%d baixado com sucesso.", i, total_items)
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

            logger.info("Todos os %d arquivos do álbum foram baixados. Iniciando o envio para o destino %d...", len(files), dest_chat_id)

            last_upload_log = time.time()
            async def upload_progress(current, total):
                nonlocal last_upload_log
                now = time.time()
                if now - last_upload_log > 5:
                    if isinstance(current, float):
                        logger.info("Progresso do envio do álbum: %.1f / %d arquivos", current, total)
                    else:
                        percent = (current / total) * 100 if total else 0
                        logger.info("Progresso do envio do álbum: %.1f%% (%d/%d bytes)", percent, current, total)
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
                progress_callback=upload_progress,
            )

            if not isinstance(sent_messages, list):
                sent_messages = [sent_messages]

            logger.info(
                "Álbum replicado com sucesso! %d itens enviados para %d.",
                len(sent_messages), dest_chat_id,
            )
            return sent_messages

        except FloodWaitError:
            raise
        except Exception as e:
            logger.error("Erro ao replicar álbum para %d: %s", dest_chat_id, e)
            return None
        finally:
            # Limpa arquivos temporários
            for path in media_files:
                if path:
                    try:
                        os.remove(path)
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
        logger.info("Processando encaminhamento de álbum (Grupo ID: %s) com %d itens. Encaminhando de %d para %d...", group_id, total_items, source_chat_id, dest_chat_id)

        try:
            message_ids = [msg.id for msg in album_messages]
            result = await self._client.forward_messages(
                entity=dest_chat_id,
                messages=message_ids,
                from_peer=source_chat_id,
            )
            if not isinstance(result, list):
                result = [result]
            logger.info(
                "Álbum encaminhado com sucesso! %d itens enviados para %d.",
                len(result), dest_chat_id,
            )
            return result
        except FloodWaitError:
            raise
        except Exception as e:
            logger.error("Erro ao encaminhar álbum: %s", e)
            return None
