"""
Wrapper para o cliente do Telethon com failover automático.
Fornece uma interface unificada para operações no Telegram,
alternando automaticamente entre Conta 1 e Conta 2 em caso de falha.
"""

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    AuthKeyError,
    UserDeactivatedBanError,
    SessionRevokedError,
    RPCError,
)
import asyncio
from src.core.config import AppConfig
from src.core.session_manager import SessionManager
from src.db.connection import Database
from src.db.repositories.accounts_repo import AccountsRepository
from src.db.models import AccountStatus
from src.utils.logger import logger

class TelegramClientWrapper:
    """
    Wrapper que abstrai o acesso ao Telegram com failover automático.

    Gerencia a conta ativa, detecta falhas críticas (ban, sessão revogada,
    FloodWait longo) e chaveia para a conta de backup quando disponível.
    """

    def __init__(self, config: AppConfig, session_manager: SessionManager, db: Database):
        self._config = config
        self._session_manager = session_manager
        self._db = db
        self._accounts_repo = AccountsRepository(db)
        self._active_account: int | None = None
        self._is_initialized = False

    @property
    def active_account(self) -> int | None:
        """Retorna o número da conta ativa."""
        return self._active_account

    @property
    def client(self) -> TelegramClient | None:
        """Retorna o TelegramClient da conta ativa."""
        return self._session_manager.get_client(self._active_account)

    async def initialize(self) -> TelegramClient:
        """
        Inicializa a conexão com o Telegram.
        Tenta Conta 1 primeiro. Se falhar e Conta 2 estiver configurada,
        tenta a Conta 2 como fallback.

        Returns:
            TelegramClient conectado e autorizado.

        Raises:
            ConnectionError: Se nenhuma conta puder ser conectada.
        """
        self._config.ensure_directories()

        # Tenta Conta 1 (primária)
        try:
            acc1 = await self._accounts_repo.get_by_id(1)
            api_id1 = acc1.api_id if acc1 else None
            api_hash1 = acc1.api_hash if acc1 else None
            phone1 = acc1.phone if acc1 else None
            client = await self._session_manager.start_client(1, api_id1, api_hash1, phone1)
            if await self._session_manager.is_authorized(1):
                self._active_account = 1
                self._is_initialized = True
                await self._update_account_status(1, AccountStatus.CONNECTED)
                logger.info("Conectado com Conta 1 (primária).")
                return client
        except Exception as e:
            logger.warning("Falha ao conectar Conta 1: %s", e)
            await self._update_account_status(1, AccountStatus.DISCONNECTED)

        # Fallback para Conta 2
        try:
            acc2 = await self._accounts_repo.get_by_id(2)
            if acc2:
                client = await self._session_manager.start_client(2, acc2.api_id, acc2.api_hash, acc2.phone)
                if await self._session_manager.is_authorized(2):
                    self._active_account = 2
                    self._is_initialized = True
                    await self._update_account_status(2, AccountStatus.CONNECTED)
                    logger.info("Conectado com Conta 2 (fallback).")
                    return client
        except Exception as e:
            logger.warning("Falha ao conectar Conta 2: %s", e)
            await self._update_account_status(2, AccountStatus.DISCONNECTED)

        raise ConnectionError(
            "Não foi possível conectar nenhuma conta do Telegram. "
            "Verifique as credenciais da API na aba Configurações da UI "
            "e se existe alguma conta logada."
        )

    async def execute(self, operation, *args, **kwargs):
        """
        Executa uma operação no Telegram com tratamento de erros e failover.

        Se a operação falhar com erro crítico (ban, sessão revogada),
        tenta automaticamente com a outra conta.

        Args:
            operation: Coroutine ou callable que recebe TelegramClient como primeiro argumento.
            *args: Argumentos adicionais para a operação.
            **kwargs: Argumentos nomeados para a operação.

        Returns:
            Resultado da operação.

        Raises:
            RuntimeError: Se o wrapper não foi inicializado.
            ConnectionError: Se a operação falhar em todas as contas.
        """
        if not self._is_initialized:
            raise RuntimeError("ClientWrapper não inicializado. Chame initialize() primeiro.")

        try:
            client = self.client
            return await operation(client, *args, **kwargs)
        except FloodWaitError as e:
            return await self._handle_flood_wait(e, operation, *args, **kwargs)
        except (AuthKeyError, UserDeactivatedBanError, SessionRevokedError) as e:
            return await self._handle_critical_error(e, operation, *args, **kwargs)
        except RPCError as e:
            logger.error("Erro RPC na conta %d: %s", self._active_account, e)
            raise
        except ConnectionError as e:
            return await self._handle_connection_error(e, operation, *args, **kwargs)

    async def _handle_flood_wait(self, error: FloodWaitError, operation, *args, **kwargs):
        """
        Trata FloodWaitError. Se o tempo for curto (<=60s), espera.
        Se for longo, tenta failover para outra conta.
        """
        wait_seconds = error.seconds
        logger.warning(
            "FloodWait na conta %d: aguardar %d segundos.",
            self._active_account, wait_seconds
        )

        if wait_seconds <= 60:
            # Espera curta — aguarda e retenta
            await asyncio.sleep(wait_seconds)
            client = self.client
            return await operation(client, *args, **kwargs)
        else:
            # Espera longa — tenta failover
            await self._update_account_status(self._active_account, AccountStatus.FLOOD_WAIT)
            switched = await self._try_failover()
            if switched:
                client = self.client
                return await operation(client, *args, **kwargs)
            else:
                # Sem alternativa, aguarda o flood
                logger.warning("Sem conta alternativa. Aguardando %d segundos.", wait_seconds)
                await asyncio.sleep(wait_seconds)
                await self._update_account_status(self._active_account, AccountStatus.CONNECTED)
                client = self.client
                return await operation(client, *args, **kwargs)

    async def _handle_critical_error(self, error: Exception, operation, *args, **kwargs):
        """
        Trata erros críticos (ban, sessão revogada).
        Marca a conta como banida e tenta failover.
        """
        logger.error(
            "Erro crítico na conta %d: %s. Tentando failover.",
            self._active_account, error
        )
        await self._update_account_status(self._active_account, AccountStatus.BANNED)
        await self._session_manager.disconnect_client(self._active_account)

        switched = await self._try_failover()
        if switched:
            client = self.client
            return await operation(client, *args, **kwargs)
        else:
            raise ConnectionError(f"Conta {self._active_account} banida/revogada e sem fallback disponível.")

    async def _handle_connection_error(self, error: Exception, operation, *args, **kwargs):
        """
        Trata erros de conexão. Tenta reconectar e, se falhar, failover.
        """
        logger.warning("Erro de conexão na conta %d: %s", self._active_account, error)

        # Tenta reconectar a conta atual
        for attempt in range(3):
            try:
                await asyncio.sleep(2 ** attempt)  # Backoff exponencial

                acc = await self._accounts_repo.get_by_id(self._active_account)
                api_id = acc.api_id if acc else None
                api_hash = acc.api_hash if acc else None
                phone = acc.phone if acc else None

                await self._session_manager.start_client(self._active_account, api_id, api_hash, phone)
                client = self.client
                return await operation(client, *args, **kwargs)
            except Exception:
                logger.debug("Tentativa %d de reconexão falhou.", attempt + 1)

        # Reconexão falhou — tenta failover
        switched = await self._try_failover()
        if switched:
            client = self.client
            return await operation(client, *args, **kwargs)
        else:
            raise ConnectionError("Falha de conexão em todas as contas após múltiplas tentativas.")

    async def _try_failover(self) -> bool:
        """
        Tenta alternar para a outra conta.

        Returns:
            True se o failover foi bem-sucedido, False caso contrário.
        """
        other_account = 2 if self._active_account == 1 else 1

        acc = await self._accounts_repo.get_by_id(other_account)
        if not acc or not acc.phone:
            logger.warning("Conta %d não configurada. Failover impossível.", other_account)
            return False

        try:
            await self._session_manager.start_client(other_account, acc.api_id, acc.api_hash, acc.phone)
            if await self._session_manager.is_authorized(other_account):
                old_account = self._active_account
                self._active_account = other_account
                await self._update_account_status(other_account, AccountStatus.CONNECTED)
                logger.info("Failover: Conta %d -> Conta %d.", old_account, other_account)
                return True
        except Exception as e:
            logger.error("Failover para conta %d falhou: %s", other_account, e)

        return False

    async def _update_account_status(self, account_id: int | None, status: AccountStatus) -> None:
        """Atualiza o status da conta no banco de dados (silencioso se falhar)."""
        if account_id is None:
            return
        try:
            await self._accounts_repo.update_status(account_id, status)
        except Exception:
            logger.debug("Não foi possível atualizar status da conta %d no DB.", account_id)

    async def disconnect(self) -> None:
        """Desconecta todas as contas e limpa o estado."""
        await self._session_manager.disconnect_all()
        self._is_initialized = False
        logger.info("ClientWrapper desconectado.")

    @property
    def is_connected(self) -> bool:
        """Retorna True se há uma conta ativa e conectada."""
        client = self.client
        return client is not None and client.is_connected()
