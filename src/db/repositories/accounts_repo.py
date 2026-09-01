"""Repositório para operações CRUD na tabela de contas do Telegram."""

from src.db.connection import Database
from src.db.models import Account, AccountStatus
from src.utils.logger import logger

class AccountsRepository:
    """Gerencia operações de banco de dados para contas do Telegram."""

    def __init__(self, db: Database):
        self._db = db

    async def create(self, account: Account) -> int:
        """Insere uma nova conta. Retorna o ID."""
        cursor = await self._db.execute(
            """INSERT INTO accounts (id, phone, api_id, api_hash, session_string, is_active, is_primary, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (account.id, account.phone, account.api_id, account.api_hash,
             account.session_string, int(account.is_active), int(account.is_primary),
             account.status.value)
        )
        logger.info("Conta %d criada: %s", account.id, account.phone)
        return cursor.lastrowid

    async def get_by_id(self, account_id: int) -> Account | None:
        """Busca uma conta pelo ID."""
        row = await self._db.fetch_one(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        return Account(**row) if row else None

    async def get_primary(self) -> Account | None:
        """Retorna a conta primária (Conta 1)."""
        row = await self._db.fetch_one(
            "SELECT * FROM accounts WHERE is_primary = 1 AND is_active = 1"
        )
        return Account(**row) if row else None

    async def get_all(self) -> list[Account]:
        """Retorna todas as contas cadastradas."""
        rows = await self._db.fetch_all("SELECT * FROM accounts ORDER BY id")
        return [Account(**row) for row in rows]

    async def update_status(self, account_id: int, status: AccountStatus) -> None:
        """Atualiza o status de uma conta."""
        await self._db.execute(
            "UPDATE accounts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status.value, account_id)
        )
        logger.debug("Status da conta %d atualizado para %s", account_id, status.value)

    async def update(self, account: Account) -> None:
        """Atualiza todos os campos de uma conta existente."""
        await self._db.execute(
            """UPDATE accounts SET phone = ?, api_id = ?, api_hash = ?, session_string = ?,
               is_active = ?, is_primary = ?, status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (account.phone, account.api_id, account.api_hash, account.session_string,
             int(account.is_active), int(account.is_primary), account.status.value, account.id)
        )

    async def delete(self, account_id: int) -> None:
        """Remove uma conta pelo ID."""
        await self._db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        logger.info("Conta %d removida.", account_id)

    async def count(self) -> int:
        """Retorna o número total de contas."""
        row = await self._db.fetch_one("SELECT COUNT(*) as total FROM accounts")
        return row["total"] if row else 0
