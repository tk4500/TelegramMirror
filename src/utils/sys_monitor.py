import asyncio
import psutil
from src.utils.disk_monitor import DiskMonitor
from src.web.ws_manager import ws_manager

class SysMonitor:
    def __init__(self, interval: int = 2):
        self.interval = interval
        self.disk_monitor = DiskMonitor()
        self._is_running = False
        self._task = None

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._is_running:
            try:
                stats = {
                    "cpu": psutil.cpu_percent(interval=None),
                    "ram": psutil.virtual_memory().percent,
                    "disk_free_mb": round(self.disk_monitor.get_free_space_mb(), 2),
                    "disk": psutil.disk_usage(str(self.disk_monitor._check_path.absolute())).percent,
                    "is_critical": self.disk_monitor.is_space_critical()
                }
                await ws_manager.broadcast("hardware_stats", stats)
            except Exception:
                pass
            await asyncio.sleep(self.interval)
