"""Gerenciador de sessões isoladas do Telethon para múltiplas contas do Telegram."""

from src.utils.logger import log_execution
from telethon import TelegramClient
from src.core.config import AppConfig
from src.utils.logger import logger

class SessionManager:
    """
    Gerencia criação, armazenamento e recuperação de sessões Telethon.
    Cada conta tem seu arquivo .session isolado em data/sessions/.
    Suporta até 2 contas simultâneas com sessões independentes.
    """

    @log_execution
    def __init__(self, config: AppConfig):
        self._config = config
        self._clients: dict[int, TelegramClient] = {}

    @log_execution
    def _get_session_path(self, account_number: int) -> str:
        """
        Retorna o caminho completo do arquivo .session para a conta.

        Args:
            account_number: Número da conta (1 ou 2).

        Returns:
            Caminho do arquivo de sessão (sem extensão .session, Telethon adiciona).
        """
        session_dir = self._config.sessions_dir
        session_dir.mkdir(parents=True, exist_ok=True)
        return str(session_dir / f"account_{account_number}")

    @log_execution
    def create_client(self, account_number: int, api_id: int | None = None, api_hash: str | None = None) -> TelegramClient:
        """
        Cria um TelegramClient para a conta especificada.
        Usa arquivo .session isolado em data/sessions/.

        Args:
            account_number: Número da conta (1 ou 2).
            api_id: API ID, opcional se já estiver configurado no banco.
            api_hash: API Hash, opcional se já estiver configurado no banco.

        Returns:
            Instância do TelegramClient configurada.
        """
        # Garante que temos pelo menos os dados da API
        if not api_id or not api_hash:
            raise ValueError(
                "API_ID e API_HASH não fornecidos. Por favor, acesse o painel "
                "e preencha as configurações da API do Telegram ao autenticar."
            )

        session_path = self._get_session_path(account_number)

        # Construtor padrao da api
        client_kwargs = {
            "session": session_path,
            "api_id": api_id,
            "api_hash": api_hash,
        }

        client = TelegramClient(**client_kwargs)

        self._clients[account_number] = client
        logger.info(
            "Client Telethon criado para conta %d",
            account_number
        )
        return client

    @log_execution
    async def start_client(self, account_number: int, api_id: int | None = None, api_hash: str | None = None, phone: str | None = None) -> TelegramClient:
        """
        Inicia e autentica o client Telethon para a conta.
        Se a sessão já existe no disco, reconecta automaticamente.
        Caso contrário, inicia o fluxo de autenticação interativo.

        Args:
            account_number: Número da conta (1 ou 2).

        Returns:
            TelegramClient conectado e autorizado.
        """
        if account_number in self._clients:
            client = self._clients[account_number]
            if client.is_connected():
                logger.debug("Conta %d já conectada, reutilizando.", account_number)
                return client
        else:
            client = self.create_client(account_number, api_id, api_hash)

        await client.start(phone=phone)
        logger.info("Conta %d conectada com sucesso.", account_number)
        return client

    @log_execution
    async def disconnect_client(self, account_number: int) -> None:
        """
        Desconecta o client de uma conta específica.

        Args:
            account_number: Número da conta (1 ou 2).
        """
        client = self._clients.get(account_number)
        if client and client.is_connected():
            await client.disconnect()
            logger.info("Conta %d desconectada.", account_number)
        self._clients.pop(account_number, None)

    @log_execution
    async def disconnect_all(self) -> None:
        """Desconecta todos os clients ativos."""
        account_numbers = list(self._clients.keys())
        for account_number in account_numbers:
            await self.disconnect_client(account_number)
        logger.info("Todos os clients desconectados.")

    @log_execution
    def get_client(self, account_number: int) -> TelegramClient | None:
        """
        Retorna o client ativo da conta, ou None se não conectado.

        Args:
            account_number: Número da conta (1 ou 2).

        Returns:
            TelegramClient ou None.
        """
        return self._clients.get(account_number)

    @log_execution
    def remove_client(self, account_number: int):
        """Remove o cliente do cache local."""
        if account_number in self._clients:
            del self._clients[account_number]

    @log_execution
    async def is_authorized(self, account_number: int) -> bool:
        """
        Verifica se a sessão da conta está autorizada no Telegram.

        Args:
            account_number: Número da conta (1 ou 2).

        Returns:
            True se autorizada, False caso contrário.
        """
        client = self._clients.get(account_number)
        if client is None:
            return False
        try:
            return await client.is_user_authorized()
        except Exception:
            logger.warning("Erro ao verificar autorização da conta %d.", account_number)
            return False

    @property
    @log_execution
    def active_clients(self) -> dict[int, TelegramClient]:
        """Retorna dicionário de clients ativos (account_number -> TelegramClient)."""
        return {
            num: client
            for num, client in self._clients.items()
            if client.is_connected()
        }

    @property
    @log_execution
    def has_active_client(self) -> bool:
        """Retorna True se houver pelo menos um client ativo."""
        return len(self.active_clients) > 0