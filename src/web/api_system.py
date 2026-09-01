from fastapi import APIRouter, Depends, Request
import os
import signal
import sys
from src.web.auth import get_current_user
from src.utils.logger import logger
import asyncio

system_router = APIRouter(prefix="/api/system", tags=["System"], dependencies=[Depends(get_current_user)])

@system_router.post("/shutdown")
async def shutdown_system(request: Request):
    logger.info("Comando de shutdown recebido via API.")
    
    # Executa o desligamento de forma assíncrona para permitir que a resposta retorne ao cliente
    async def shutdown_task():
        await asyncio.sleep(1) # Dá tempo para a requisição retornar com sucesso
        
        # Envia o signal que o desktop.py / main monitoram para desligar o uvicorn
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0)
        else:
            os.kill(os.getpid(), signal.SIGINT)
            
        # Fallback de segurança se o signal não for pego pela thead principal
        await asyncio.sleep(3)
        os._exit(0)
        
    asyncio.create_task(shutdown_task())
    return {"message": "Desligamento iniciado com segurança.", "status": "shutting_down"}
