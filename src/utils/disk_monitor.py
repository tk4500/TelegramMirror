"""Monitor de espaço livre em disco."""

import shutil
from pathlib import Path
from src.utils.logger import logger


class DiskMonitor:
    """Monitora o espaço livre em disco para evitar travamentos."""

    def __init__(self, check_path: str = "data/temp", min_free_mb: int = 500):
        self._check_path = Path(check_path)
        self._check_path.mkdir(parents=True, exist_ok=True)
        self._min_free_bytes = min_free_mb * 1024 * 1024

    def get_free_space_mb(self) -> float:
        usage = shutil.disk_usage(str(self._check_path.absolute()))
        return usage.free / (1024 * 1024)

    def is_space_critical(self) -> bool:
        usage = shutil.disk_usage(str(self._check_path.absolute()))
        is_critical = usage.free < self._min_free_bytes
        if is_critical:
            logger.warning("ESPAÇO EM DISCO CRÍTICO! %.2f MB livres", usage.free / (1024 * 1024))
        return is_critical

    def check_and_raise_if_critical(self) -> None:
        if self.is_space_critical():
            raise IOError("Espaço em disco insuficiente.")
