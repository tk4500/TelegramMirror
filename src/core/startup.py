"""Orquestrador de inicialização do TelegramMirror."""

import sys
import asyncio
from src.core.config import AppConfig
from src.core.session_manager import SessionManager
from src.core.client_wrapper import TelegramClientWrapper
from src.db.connection import Database
from src.db.repositories.accounts_repo import AccountsRepository
from src.db.models import Account, AccountStatus
from src.utils.disk_monitor import DiskMonitor
from src.utils.temp_scanner import TempScanner
from src.utils.network_monitor import NetworkMonitor
from src.utils.logger import logger
from src.core.orchestrator import CopyOrchestrator
from src.utils.sys_monitor import SysMonitor

class StartupManager:
    def __init__(self):
        self.config = AppConfig()
        self.db = Database(str(self.config.db_path))
        self.session_manager = SessionManager(self.config)
        self.client_wrapper = TelegramClientWrapper(self.config, self.session_manager, self.db)
        self.orchestrator = CopyOrchestrator(self.client_wrapper, self.db)
        self.sys_monitor = SysMonitor()

    async def initialize(self) -> bool:
        try:
            if self.config.debug_mode:
                logger.info("Modo debug global habilitado via hooks dinâmicos")

            logger.info("=== Iniciando TelegramMirror ===")
            self.config.ensure_directories()
            TempScanner(str(self.config.temp_dir)).cleanup()

            DiskMonitor(str(self.config.temp_dir)).check_and_raise_if_critical()
            net = NetworkMonitor()
            if not await net.is_internet_available(timeout=5.0):
                logger.warning("Internet indisponível no startup. Aguardando...")
                await net.wait_for_network()

            await self.db.connect()
            await self._ensure_accounts_in_db()

            # Injeta no app state global ANTES de inicializar o client_wrapper,
            # pois se o initialize falhar e der raise num except, ele nao injeta o db no app.state
            from src.web.app import app
            app.state.db = self.db
            app.state.client_wrapper = self.client_wrapper
            app.state.orchestrator = self.orchestrator
            app.state.config = self.config

            # O initialize do ClientWrapper falhará se não tiver as accounts configuradas (API_ID, HASH e Phone)
            # Mas se falhar, queremos apenas registrar o log sem abortar a API para o frontend.
            try:
                await self.client_wrapper.initialize()
            except Exception as ex:
                logger.warning("Não foi possível inicializar as conexões do Telegram no momento: %s", ex)

            # Inicia o monitor de hardware
            await self.sys_monitor.start()

            logger.info("=== Sistema pronto para operar ===")
            return True
        except Exception as e:
            logger.critical("Falha fatal na inicialização: %s", e)

            # Injetamos o state básico mesmo numa falha grave para a API não crashar ao injetar Request
            from src.web.app import app
            if not hasattr(app.state, 'db'):
                app.state.db = self.db
            if not hasattr(app.state, 'client_wrapper'):
                app.state.client_wrapper = self.client_wrapper
            if not hasattr(app.state, 'orchestrator'):
                app.state.orchestrator = self.orchestrator
            app.state.config = self.config

            return False

    async def shutdown(self):
        await self.sys_monitor.stop()
        await self.client_wrapper.disconnect()
        await self.db.close()
        logger.info("=== Sistema encerrado ===")

    async def _ensure_accounts_in_db(self):
        repo = AccountsRepository(self.db)

        # Garante que sempre existirão as duas contas (ID 1 e ID 2) no banco,
        # mesmo que elas estejam vazias e desconectadas inicialmente
        if not await repo.get_by_id(1):
            acc1 = Account(
                id=1, phone="unconfigured_1", api_id=0, api_hash="",
                is_primary=True, status=AccountStatus.DISCONNECTED
            )
            await repo.create(acc1)

        if not await repo.get_by_id(2):
            acc2 = Account(
                id=2, phone="unconfigured_2", api_id=0, api_hash="",
                is_primary=False, status=AccountStatus.DISCONNECTED
            )
            await repo.create(acc2)
