"""Configuração centralizada do TelegramMirror usando variáveis de ambiente."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
import sys
import os

# No modo frozen (PyInstaller), carregamos o .env que foi embutido no executável (.env.embedded)
# Se estiver rodando normalmente via script, usamos o .env na raiz do projeto.
if getattr(sys, 'frozen', False):
    env_path = os.path.join(sys._MEIPASS, '.env.embedded')
else:
    env_path = '.env'

class AppConfig(BaseSettings):
    """
    Configuração geral da aplicação.
    Carrega automaticamente do arquivo .env na raiz do projeto ou .env.embedded se compilado.
    """
    model_config = SettingsConfigDict(
        env_file=env_path,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Diretórios da aplicação
    data_dir: Path = Path("data")
    sessions_dir: Path = Path("data/sessions")
    temp_dir: Path = Path("data/temp")
    db_path: Path = Path("data/telegram_mirror.db")

    # Perfil de velocidade padrão
    default_speed_profile: str = "safe"

    # Flag global de debug detalhado
    debug_mode: bool = False

    def ensure_directories(self) -> None:
        """Cria os diretórios necessários da aplicação se não existirem."""
        for directory in [self.data_dir, self.sessions_dir, self.temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)
