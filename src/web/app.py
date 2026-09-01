from fastapi import FastAPI, Request, status, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from src.utils.logger import logger
from src.web.auth import auth_router
from src.web.api_chats import chats_router
from src.web.api_config import config_router
from src.web.api_orchestrator import flow_router
from src.web.api_hardware import hardware_router
from src.web.api_telegram_auth import tg_auth_router
from src.web.api_checkpoint import checkpoint_router
from src.web.api_logs import logs_router
from src.web.api_system import system_router
from src.web.ws_manager import ws_manager
from src.core.startup import StartupManager

startup_manager = StartupManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa tudo DENTRO do event loop do FastAPI
    await startup_manager.initialize()
    yield
    # Encerra tudo quando o servidor cair
    await startup_manager.shutdown()

app = FastAPI(title="TelegramMirror API", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Erro na API [%s %s]: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "Internal Error", "detail": str(exc)})

app.include_router(auth_router)
app.include_router(tg_auth_router)
app.include_router(chats_router)
app.include_router(config_router)
app.include_router(flow_router)
app.include_router(hardware_router)
app.include_router(checkpoint_router)
app.include_router(system_router)
app.include_router(logs_router)

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ws_manager.disconnect(websocket)

import sys
import os

# Mount assets ANTES do / que pega o index.html, senao o /api/assets é capturado
if getattr(sys, 'frozen', False):
    assets_dir = Path(sys._MEIPASS) / "assets"
else:
    assets_dir = Path(__file__).parent.parent.parent / "assets"
assets_dir.mkdir(exist_ok=True)
app.mount("/api/assets", StaticFiles(directory=str(assets_dir)), name="assets")

static_dir = Path(__file__).parent.parent.parent / "frontend"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")