"""Gerenciador de conexão assíncrona com o SQLite usando aiosqlite."""

import aiosqlite
from pathlib import Path
from src.utils.logger import logger

class Database:
    """
    Gerenciador de conexão assíncrona com SQLite.
    Suporta uso como context manager async e fornece métodos
    utilitários para queries comuns.
    """

    def __init__(self, db_path: str = "data/telegram_mirror.db"):
        self._db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Abre a conexão com o banco, cria diretório e aplica o schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self._db_path))
        self._connection.row_factory = aiosqlite.Row

        # PRAGMAs de performance e integridade
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")

        # Aplicar schema
        await self._apply_schema()
        logger.info("Banco de dados conectado: %s", self._db_path)

    async def _apply_schema(self) -> None:
        """Lê e executa o schema.sql para criar/atualizar tabelas."""
        import sys

        # Resolve o caminho do schema considerando quando roda como executável do PyInstaller
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent.parent.parent

        schema_path = base_path / "src" / "db" / "schema.sql"

        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
            # Remove PRAGMAs do schema (já executados acima)
            lines = [
                line for line in schema_sql.split("\n")
                if not line.strip().upper().startswith("PRAGMA")
            ]
            await self._connection.executescript("\n".join(lines))
            logger.debug("Schema aplicado com sucesso.")
        else:
            logger.error(f"Arquivo schema.sql não encontrado em {schema_path}")

    async def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Conexão com banco de dados fechada.")

    async def execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Executa uma query com commit automático. Retorna o cursor."""
        self._ensure_connected()
        cursor = await self._connection.execute(query, params)
        await self._connection.commit()
        return cursor

    async def execute_many(self, query: str, params_list: list[tuple]) -> None:
        """Executa a mesma query para múltiplos conjuntos de parâmetros."""
        self._ensure_connected()
        await self._connection.executemany(query, params_list)
        await self._connection.commit()

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Executa query e retorna a primeira linha como dicionário, ou None."""
        self._ensure_connected()
        cursor = await self._connection.execute(query, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Executa query e retorna todas as linhas como lista de dicionários."""
        self._ensure_connected()
        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    def _ensure_connected(self) -> None:
        """Verifica se há uma conexão ativa."""
        if self._connection is None:
            raise RuntimeError("Banco de dados não conectado. Chame connect() primeiro.")

    async def __aenter__(self) -> "Database":
        """Suporte a context manager async."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Fecha a conexão ao sair do context manager."""
        await self.close()

    @property
    def is_connected(self) -> bool:
        """Retorna True se há uma conexão ativa com o banco."""
        return self._connection is not None