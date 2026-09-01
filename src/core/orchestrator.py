from src.utils.logger import log_execution
import asyncio
import json
import datetime
from src.db.models import CopyMode, CopyScope, SpeedProfile
from src.web.ws_manager import ws_manager
from src.utils.logger import logger, ws_log, TelethonEncoder
from src.services.history.history_backfill import HistoryBackfill
from src.services.listeners.realtime_listener import RealtimeListener
from src.db.repositories.accounts_repo import AccountsRepository

class CopyOrchestrator:
    @log_execution
    def __init__(self, client_wrapper, db):
        self.client_wrapper = client_wrapper
        self.db = db
        self._current_engine = None
        self._is_running = False
        self._is_paused = False

    @property
    @log_execution
    def is_running(self):
        return self._is_running

    @log_execution
    async def _on_progress(self, processed, failed, last_id):
        # Avança o checkpoint progressivamente
        if hasattr(self, '_current_checkpoint_id') and self._current_checkpoint_id:
            from src.db.repositories.checkpoints_repo import CheckpointsRepository
            repo = CheckpointsRepository(self.db)

            # Puxa os dados antigos do checkpoint para não zerarmos a contagem total a cada play/pause
            old_cp = await repo.get_by_id(self._current_checkpoint_id)
            total_copied = (old_cp.total_copied if old_cp else 0) + processed
            total_failed = (old_cp.total_failed if old_cp else 0) + failed

            await repo.update_progress(self._current_checkpoint_id, last_id, total_copied, total_failed)

            # Limpamos do banco de falhas apenas a mensagem que ACABOU de ser processada com sucesso
            # ou pulada legitimamente (vazia). O `<` causava exclusao de falhas reais passadas.
            await self.db.execute("DELETE FROM failed_messages WHERE checkpoint_id = ? AND message_id = ?", (self._current_checkpoint_id, last_id))

        await ws_manager.broadcast("progress", {"processed": processed, "failed": failed})

    @log_execution
    async def _on_message(self, message, sent):
        msg_id = getattr(message, 'id', 'Desconhecido')
        log_msg = f"Mensagem #{msg_id} copiada/encaminhada com sucesso."
        await ws_log(log_msg, "OK")

    @log_execution
    async def _on_error(self, message, error):
        error_msg = str(error)
        await ws_log(f"Erro: {error_msg}", "error")

        if hasattr(self, '_current_checkpoint_id') and self._current_checkpoint_id and message:
            from src.db.models import FailedMessage, FailedMessageStatus
            from src.db.repositories.failed_repo import FailedMessagesRepository

            original_data_json = None
            try:
                # Transforma o objeto Message do Telethon em um dict e converte em JSON estruturado
                original_data_json = json.dumps(message.to_dict(), cls=TelethonEncoder, indent=2)
            except Exception as e:
                original_data_json = f"Erro ao extrair JSON nativo da mensagem: {e}"

            repo = FailedMessagesRepository(self.db)
            fail = FailedMessage(
                id=0,
                checkpoint_id=self._current_checkpoint_id,
                message_id=message.id,
                error_message=error_msg,
                error_type=type(error).__name__,
                retry_count=0,
                status=FailedMessageStatus.PENDING,
                original_data=original_data_json
            )
            # Salvando mensagem que falhou no banco
            await repo.create(fail)

    @log_execution
    async def start_routine(self, source_chat_id: int, dest_chat_id: int, mode: CopyMode, scope: CopyScope, speed_profile: SpeedProfile, selective_ids: list[int] = None, debug_mode: bool = False):
        if self._is_running:
            return

        self._is_running = True
        self._is_paused = False
        await ws_manager.broadcast("status_change", {"status": "running"})

        mode_text = "Cópia Seletiva" if selective_ids else mode.value
        await ws_log(f"Iniciando engine: {mode_text} | {scope.value}...", "info")

        try:
            rules = await self.db.fetch_all("SELECT * FROM replacement_rules WHERE is_active = 1")
            from src.db.models import ReplacementRule
            rule_models = [ReplacementRule(**r) for r in rules]

            client = self.client_wrapper.client

            if selective_ids or scope in (CopyScope.HISTORY, CopyScope.CHECKPOINT):
                from src.services.checkpoint_service import CheckpointService
                cs = CheckpointService(self.db)
                cp = await cs.get_or_create_checkpoint(self.client_wrapper.active_account, source_chat_id, dest_chat_id, mode, scope, debug_mode)

                # Se for cópia seletiva, ignora o checkpoint numérico tradicional
                start_id = 0 if selective_ids else (cp.last_message_id if scope == CopyScope.CHECKPOINT else 0)
                self._current_checkpoint_id = cp.id

                # Lê configuração premium
                settings_rows = await self.db.fetch_all("SELECT * FROM app_settings WHERE key = 'premium_account'")
                preserve_emojis = False
                if settings_rows and settings_rows[0]['value'] in ('true', '1', 'yes'):
                    preserve_emojis = True

                self._current_engine = HistoryBackfill(client, source_chat_id, dest_chat_id, mode, speed_profile, rule_models, debug_mode=debug_mode, preserve_custom_emojis=preserve_emojis)
                self._current_engine.on_progress(self._on_progress)
                self._current_engine.on_error(self._on_error)
                self._current_engine.on_message_processed(self._on_message)

                if selective_ids:
                    await self._current_engine.start_selective(selective_ids)
                else:
                    await self._current_engine.start(start_from_id=start_id)

            else:
                settings_rows = await self.db.fetch_all("SELECT * FROM app_settings WHERE key = 'premium_account'")
                preserve_emojis = False
                if settings_rows and settings_rows[0]['value'] in ('true', '1', 'yes'):
                    preserve_emojis = True

                self._current_engine = RealtimeListener(client, source_chat_id, dest_chat_id, mode, rule_models, debug_mode=debug_mode, preserve_custom_emojis=preserve_emojis)
                self._current_engine.on_error(self._on_error)
                self._current_engine.on_message_processed(self._on_message)
                await self._current_engine.start()
                while self._is_running:
                    await asyncio.sleep(1)

            await ws_log("Rotina finalizada.", "info")
        except Exception as e:
            logger.error("Erro critico no Orquestrador: %s", e)
            await ws_log(f"Erro critico: {e}", "error")
        finally:
            self._is_running = False
            self._current_engine = None
            await ws_manager.broadcast("status_change", {"status": "idle"})

    @log_execution
    async def pause_routine(self):
        if self._current_engine and hasattr(self._current_engine, 'pause'):
            await self._current_engine.pause()
            self._is_paused = True
            await ws_manager.broadcast("status_change", {"status": "paused"})
            await ws_log("Processo pausado.", "warning")

    @log_execution
    async def stop_routine(self):
        if self._current_engine:
            await self._current_engine.stop()
            self._is_running = False
            self._is_paused = False
            await ws_manager.broadcast("status_change", {"status": "idle"})
            await ws_log("Processo parado pelo usuario.", "warning")

    @log_execution
    def get_status(self):
        return {
            "is_running": self._is_running,
            "is_paused": self._is_paused
        }