"""Cache local de fotos de perfil (avatares) de chats do Telegram."""

from pathlib import Path
from telethon import TelegramClient
from src.utils.logger import logger

class MediaCache:
    """
    Gerencia o download e cache local das fotos de perfil
    de canais e grupos para exibição no painel web.
    """

    def __init__(self, client: TelegramClient, cache_dir: str = "data/cache/avatars"):
        self._client = client
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, chat_id: int) -> Path:
        """Retorna o caminho do avatar em cache para um chat."""
        return self._cache_dir / f"{chat_id}.jpg"

    def has_cached(self, chat_id: int) -> bool:
        """Verifica se o avatar do chat já está em cache."""
        return self._get_cache_path(chat_id).exists()

    async def get_avatar(self, chat_id: int, force_refresh: bool = False) -> str | None:
        """
        Retorna o caminho do avatar do chat.
        Baixa se não estiver em cache ou se force_refresh=True.

        Args:
            chat_id: ID do chat.
            force_refresh: Forçar re-download mesmo se já em cache.

        Returns:
            Caminho do arquivo de avatar ou None se não disponível.
        """
        cache_path = self._get_cache_path(chat_id)

        if cache_path.exists() and not force_refresh:
            return str(cache_path)

        try:
            entity = await self._client.get_entity(chat_id)
            result = await self._client.download_profile_photo(
                entity, file=str(cache_path), download_big=False
            )
            if result:
                logger.debug("Avatar do chat %d baixado e cacheado.", chat_id)
                return str(cache_path)
            else:
                logger.debug("Chat %d não tem foto de perfil.", chat_id)
                return None
        except Exception as e:
            logger.warning("Erro ao baixar avatar do chat %d: %s", chat_id, e)
            return None

    async def get_avatars_batch(self, chat_ids: list[int]) -> dict[int, str | None]:
        """
        Baixa avatares para múltiplos chats.

        Returns:
            Dicionário chat_id -> caminho do avatar (ou None).
        """
        results: dict[int, str | None] = {}
        for chat_id in chat_ids:
            results[chat_id] = await self.get_avatar(chat_id)
        logger.info("Avatares processados: %d/%d disponíveis.",
                     sum(1 for v in results.values() if v), len(chat_ids))
        return results

    def clear_cache(self) -> int:
        """Remove todos os avatares em cache. Retorna quantos foram removidos."""
        count = 0
        for file in self._cache_dir.glob("*.jpg"):
            try:
                file.unlink()
                count += 1
            except OSError:
                pass
        logger.info("Cache de avatares limpo: %d arquivos removidos.", count)
        return count

    def get_cache_size(self) -> int:
        """Retorna o tamanho total do cache em bytes."""
        return sum(f.stat().st_size for f in self._cache_dir.glob("*") if f.is_file())
