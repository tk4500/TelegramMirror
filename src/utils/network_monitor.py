"""Monitor de conectividade e watchdog de rede."""

import asyncio
import socket
from src.utils.logger import logger


class NetworkMonitor:
    """Monitora ativamente a conectividade com a internet."""

    def __init__(self, check_host: str = "1.1.1.1", check_port: int = 53):
        self._check_host = check_host
        self._check_port = check_port
        self._is_connected = True
        self._initial_delay = 2.0
        self._max_delay = 60.0
        self._multiplier = 2.0

    async def is_internet_available(self, timeout: float = 3.0) -> bool:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: socket.create_connection((self._check_host, self._check_port), timeout=timeout))
            if not self._is_connected:
                logger.info("🌐 Conexão com a internet restaurada!")
                self._is_connected = True
            return True
        except OSError:
            if self._is_connected:
                logger.warning("🔌 Conexão com a internet perdida! Entrando em modo WAITING_NETWORK.")
                self._is_connected = False
            return False

    async def wait_for_network(self) -> None:
        if await self.is_internet_available():
            return
        delay = self._initial_delay
        while not await self.is_internet_available():
            logger.debug("Aguardando rede... próxima tentativa em %.1f segundos", delay)
            await asyncio.sleep(delay)
            delay = min(delay * self._multiplier, self._max_delay)
