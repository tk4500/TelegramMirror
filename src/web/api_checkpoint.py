from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from src.web.auth import get_current_user
from src.db.repositories.checkpoints_repo import CheckpointsRepository
from src.services.checkpoint_service import CheckpointService
from src.db.models import CopyMode, CopyScope

checkpoint_router = APIRouter(prefix="/api/checkpoint", tags=["Checkpoints"], dependencies=[Depends(get_current_user)])

class CheckpointQuery(BaseModel):
    source_chat_id: int
    dest_chat_id: int

class CheckpointUpdate(BaseModel):
    source_chat_id: int
    dest_chat_id: int
    mode: str
    scope: str
    message_id: int

@checkpoint_router.post("/current")
async def get_current_checkpoint(payload: CheckpointQuery, request: Request):
    cw = request.app.state.client_wrapper
    if not cw or not cw.active_account:
        return {"error": "Sem conta ativa"}

    db = request.app.state.db
    repo = CheckpointsRepository(db)
    cp = await repo.get_by_chat_pair(cw.active_account, payload.source_chat_id, payload.dest_chat_id)

    if not cp:
        return {"checkpoint": None}
    return {"checkpoint": cp.model_dump()}

@checkpoint_router.post("/set-position")
async def set_checkpoint_position(payload: CheckpointUpdate, request: Request):
    cw = request.app.state.client_wrapper
    if not cw or not cw.active_account:
        return {"error": "Sem conta ativa"}

    db = request.app.state.db
    repo = CheckpointsRepository(db)
    cs = CheckpointService(db)

    # Forca criar se nao existir
    mode = CopyMode(payload.mode)
    scope = CopyScope(payload.scope)
    cp = await cs.get_or_create_checkpoint(cw.active_account, payload.source_chat_id, payload.dest_chat_id, mode, scope)

    # Reduz em 1 o ID da mensagem para compensar o comportamento exclusivo (min_id > X) da API do Telethon
    # Assim, ao dar resume, a própria mensagem selecionada no frontend será a primeira a ser verificada e copiada.
    adjusted_id = max(0, payload.message_id - 1)
    await repo.set_position(cp.id, adjusted_id)
    return {"message": "Posição atualizada com sucesso"}
