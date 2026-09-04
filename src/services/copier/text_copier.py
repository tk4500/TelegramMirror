"""
Módulo de cópia por replicação de mensagens de texto.
Recria mensagens preservando formatação, entidades e metadados.
"""

from src.utils.logger import log_execution
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError, MessageTooLongError
import asyncio
import time
import os
from src.services.copier.entity_parser import EntityParser, ParsedMessage
from src.utils.logger import logger
from src.utils.fast_telethon import download_file, upload_file

class TextCopier:
    """
    Copia mensagens recriando o conteúdo no destino (modo Replicar).
    Preserva texto, formatação, entidades, links ocultos, menções,
    emojis customizados e spoilers.
    """

    @log_execution
    def __init__(self, client: TelegramClient):
        self._client = client
        self._parser = EntityParser()

    @log_execution
    async def replicate_message(
        self,
        dest_chat_id: int,
        message: Message,
        parsed_override: ParsedMessage | None = None,
        preloader=None
    ) -> Message | None:
        """
        Replica uma mensagem de texto no destino preservando toda a formatação.

        Args:
            dest_chat_id: ID do chat de destino.
            message: Mensagem original a ser replicada.
            parsed_override: Se fornecido, utiliza os dados já cacheados (como Emojis parseados)

        Returns:
            Mensagem enviada ou None se falhou.
        """
        # Refaz o fetch da mensagem para renovar o file_reference (evita erro de expiração)
        try:
            if message.chat_id:
                fresh_msg = await self._client.get_messages(message.chat_id, ids=message.id)
                if fresh_msg:
                    message = fresh_msg
        except Exception as e:
            logger.warning("Não foi possível refazer o fetch da msg %d no copier: %s", message.id, e)

        parsed = parsed_override if parsed_override else self._parser.parse_message(message)

        if not parsed.text and not parsed.has_media:
            logger.debug("Mensagem %d sem conteúdo replicável.", message.id)
            return None

        try:
            # Mensagem apenas texto (sem mídia)
            if not parsed.has_media:
                return await self._send_text(dest_chat_id, parsed)
            else:
                # Mensagem com mídia — envia com legenda
                return await self._send_media_with_caption(dest_chat_id, message, parsed, preloader=preloader)
        except MessageTooLongError:
            logger.error("Mensagem %d muito longa para replicar.", message.id)
            return None
        except FloodWaitError:
            raise  # Propaga para o handler de nível superior
        except Exception as e:
            logger.error("Erro ao replicar mensagem %d: %s", message.id, e)
            return None

    @log_execution
    async def _send_text(self, dest_chat_id: int, parsed: ParsedMessage, reply_to: int | None = None) -> Message | None:
        """Envia uma mensagem de texto puro com entidades."""
        entities = self._parser.clone_entities(parsed.entities)
        sent = await self._client.send_message(
            entity=dest_chat_id,
            message=parsed.text,
            formatting_entities=entities,
            parse_mode=None,
            link_preview=False,
            reply_to=reply_to,
        )
        logger.debug("Texto replicado para %d.", dest_chat_id)
        return sent

    @log_execution
    async def _send_media_with_caption(
        self,
        dest_chat_id: int,
        original: Message,
        parsed: ParsedMessage,
        preloader=None
    ) -> Message | None:
        """
        Envia mídia (foto/vídeo/documento) com legenda e entidades preservadas.
        Se preloader estiver presente, aguarda e usa o InputFile já feito upload.
        """
        entities = self._parser.clone_entities(parsed.entities)

        try:
            if preloader:
                media_file = await preloader.get_preloaded(original.id)
                is_preloaded = True
            else:
                ext = getattr(original.file, "ext", "")
                file_name = getattr(original.file, "name", "")
                if not file_name:
                    file_name = f"media_{original.id}{ext}"
                media_path = f"data/temp/{original.id}_{int(time.time())}{ext}"
                
                with open(media_path, "wb") as f:
                    file_size = getattr(original.file, "size", 0)
                    await download_file(self._client, original.media, f, size=file_size)
                    
                if not os.path.exists(media_path) or os.path.getsize(media_path) == 0:
                    media_file = None
                else:
                    with open(media_path, "rb") as f:
                        media_file = await upload_file(self._client, f)
                        media_file.name = file_name
                        
                    try:
                        os.remove(media_path)
                    except Exception:
                        pass
                is_preloaded = False

            if media_file is None:
                logger.warning("Não foi possível obter a mídia da mensagem %d.", original.id)
                # Fallback: envia só o texto se houver
                if parsed.text:
                    return await self._send_text(dest_chat_id, parsed)
                return None

            # Limite de 4096 caracteres para contas Premium
            caption = parsed.text or ""
            is_split = False
            if len(caption) > 4096:
                is_split = True
                send_caption = ""
                send_entities = []
            else:
                send_caption = caption
                send_entities = entities

            # Reenvia preservando qualidade
            sent = await self._client.send_file(
                entity=dest_chat_id,
                file=media_file,
                caption=send_caption,
                formatting_entities=send_entities,
                parse_mode=None,
                force_document=self._is_document(original),
            )
            logger.debug("Mídia replicada para %d.", dest_chat_id)

            if sent and is_split:
                await self._send_text(dest_chat_id, parsed, reply_to=sent.id)

            return sent

        except MessageTooLongError as e:
            # Caso a legenda seja muito grande e o Telethon não truncou sozinho
            logger.error("Erro ao replicar mídia da mensagem %d: Legenda muito longa. A mensagem não foi copiada. (Detalhe: %s)", original.id, e)
            raise e
        except Exception as e:
            error_details = str(e)
            if "caption is too long" in error_details.lower():
                 logger.error(f"Erro ao replicar mídia da mensagem {original.id}: Legenda muito grande (4096 chars máx). Original tem {len(parsed.text or '')} chars.")
                 raise Exception(f"Legenda muito grande (4096 caracteres permitidos). Reduza a legenda.")
            else:
                 logger.error("Erro ao replicar mídia da mensagem %d: %s", original.id, e)
                 raise e

    @staticmethod
    @log_execution
    def _is_document(message: Message) -> bool:
        """Verifica se a mídia é um documento (não foto/vídeo inline)."""
        from telethon.tl.types import MessageMediaDocument
        if isinstance(message.media, MessageMediaDocument):
            doc = message.media.document
            if doc and hasattr(doc, "mime_type"):
                # Se não for foto/vídeo/gif, trata como documento
                mime = doc.mime_type or ""
                if not mime.startswith(("image/", "video/")) and "gif" not in mime:
                    return True
        return False

    @log_execution
    async def replicate_batch(
        self,
        dest_chat_id: int,
        messages: list[Message],
        delay: float = 1.0,
    ) -> list[Message | None]:
        """
        Replica múltiplas mensagens em lote com delay anti-flood.

        Returns:
            Lista de mensagens enviadas (None para falhas).
        """
        results: list[Message | None] = []

        for msg in messages:
            try:
                result = await self.replicate_message(dest_chat_id, msg)
                results.append(result)
            except FloodWaitError as e:
                logger.warning("FloodWait no batch: aguardando %ds.", e.seconds)
                await asyncio.sleep(e.seconds)
                try:
                    result = await self.replicate_message(dest_chat_id, msg)
                    results.append(result)
                except Exception:
                    results.append(None)
            except Exception as e:
                logger.error("Erro no batch replicar msg %d: %s", msg.id, e)
                results.append(None)

            if delay > 0:
                await asyncio.sleep(delay)

        logger.info(
            "Batch replicate concluído: %d/%d mensagens replicadas.",
            sum(1 for r in results if r is not None),
            len(messages),
        )
        return results
