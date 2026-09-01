"""Scanner para limpeza de arquivos temporários deixados após crashes."""

from pathlib import Path
from src.utils.logger import logger


class TempScanner:
    """Varre e limpa arquivos temporários."""

    def __init__(self, temp_dir: str = "data/temp"):
        self._temp_dir = Path(temp_dir)

    def scan_residuals(self) -> list[Path]:
        if not self._temp_dir.exists():
            return []
        residuals = [f for f in self._temp_dir.glob("**/*") if f.is_file()]
        if residuals:
            total_size_mb = sum(f.stat().st_size for f in residuals) / (1024 * 1024)
            logger.warning("Encontrados %d arquivos temporários residuais (%.2f MB).", len(residuals), total_size_mb)
        return residuals

    def cleanup(self) -> int:
        residuals = self.scan_residuals()
        if not residuals:
            return 0
        count = 0
        for file in residuals:
            try:
                file.unlink()
                count += 1
            except OSError as e:
                logger.error("Falha ao remover %s: %s", file, e)
        if count > 0:
            logger.info("Limpeza: %d arquivos removidos com sucesso.", count)
        return count
