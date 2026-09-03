from fastapi import APIRouter, Depends, Request
import psutil
from src.web.auth import get_current_user
from src.utils.disk_monitor import DiskMonitor

hardware_router = APIRouter(prefix="/api/hardware", tags=["Hardware"], dependencies=[Depends(get_current_user)])

@hardware_router.get("/stats")
async def get_hardware_stats(request: Request):
    cpu_percent = psutil.cpu_percent(interval=0.1)
    
    ram = psutil.virtual_memory()
    ram_percent = ram.percent
    
    disk_monitor = DiskMonitor()
    disk_free_gb = disk_monitor.get_free_space_gb()
    
    disk = psutil.disk_usage(str(disk_monitor._check_path.absolute()))
    disk_percent = disk.percent
    
    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "disk_free_gb": disk_free_gb,
        "disk_percent": disk_percent,
        "is_disk_critical": disk_monitor.is_space_critical()
    }
