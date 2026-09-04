from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from src.web.auth import get_current_user
from src.db.models import CopyMode, CopyScope, SpeedProfile
from src.utils.logger import logger
import asyncio

flow_router = APIRouter(prefix="/api/flow", tags=["Flow Control"], dependencies=[Depends(get_current_user)])

class StartRequest(BaseModel):
    source_chat_id: int
    dest_chat_id: int
    mode: str
    scope: str
    speed_profile: str = "safe"
    selective_ids: list[int] = []
    debug_mode: bool = False
    download_only: bool = False

@flow_router.post("/start")
async def start_flow(payload: StartRequest, request: Request):
    orchestrator = request.app.state.orchestrator
    if orchestrator.is_running:
        raise HTTPException(status_code=400, detail="Uma cópia já está em andamento.")
    try:
        mode = CopyMode(payload.mode)
        scope = CopyScope(payload.scope)
        speed = SpeedProfile(payload.speed_profile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    asyncio.create_task(
        orchestrator.start_routine(
            source_chat_id=payload.source_chat_id,
            dest_chat_id=payload.dest_chat_id,
            mode=mode, scope=scope, speed_profile=speed,
            selective_ids=payload.selective_ids,
            debug_mode=payload.debug_mode,
            download_only=payload.download_only
        )
    )
    return {"message": "Rotina iniciada", "status": "started"}

@flow_router.post("/pause")
async def pause_flow(request: Request):
    orchestrator = request.app.state.orchestrator
    if not orchestrator.is_running:
        return {"message": "Nenhuma cópia em andamento", "status": "idle"}
    await orchestrator.pause_routine()
    return {"message": "Rotina pausada", "status": "paused"}

@flow_router.post("/stop")
async def stop_flow(request: Request):
    orchestrator = request.app.state.orchestrator
    if not orchestrator.is_running:
        return {"message": "Nenhuma cópia em andamento", "status": "idle"}
    await orchestrator.stop_routine()
    return {"message": "Rotina interrompida", "status": "stopped"}

@flow_router.get("/status")
async def get_flow_status(request: Request):
    orchestrator = request.app.state.orchestrator
    return orchestrator.get_status()

@flow_router.post("/retry/{checkpoint_id}")
async def retry_failed(checkpoint_id: int, request: Request):
    client_wrapper = request.app.state.client_wrapper
    db = request.app.state.db
    from src.services.retry_worker import RetryWorker
    from src.db.repositories.checkpoints_repo import CheckpointsRepository

    cp_repo = CheckpointsRepository(db)
    cp = await cp_repo.get_by_id(checkpoint_id)
    if not cp:
        return {"error": "Checkpoint not found"}

    worker = RetryWorker(client_wrapper.client, db)
    asyncio.create_task(worker.retry_pending(
        checkpoint_id=cp.id, dest_chat_id=cp.dest_chat_id, source_chat_id=cp.source_chat_id
    ))
    return {"message": "Retry worker iniciado em background.", "status": "retrying"}
