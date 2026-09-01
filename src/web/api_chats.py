"""Rotas de API para Contas, Chats e Falhas."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from src.web.auth import get_current_user
from src.services.chat_service import ChatService
from src.db.repositories.accounts_repo import AccountsRepository
from src.db.repositories.failed_repo import FailedMessagesRepository
from src.utils.media_cache import MediaCache
from pathlib import Path
import asyncio

chats_router = APIRouter(prefix="/api", tags=["Chats & Accounts"])

@chats_router.get("/accounts", dependencies=[Depends(get_current_user)])
async def get_accounts(request: Request):
    db = request.app.state.db
    client_wrapper = request.app.state.client_wrapper
    repo = AccountsRepository(db)
    
    accounts_models = await repo.get_all()
    accounts = [{"id": a.id, "phone": a.phone, "status": a.status.value, "is_primary": a.is_primary} for a in accounts_models]
    
    return {
        "accounts": accounts,
        "active_account": client_wrapper.active_account if client_wrapper else None
    }

@chats_router.get("/chats", dependencies=[Depends(get_current_user)])
async def get_chats(request: Request):
    client_wrapper = request.app.state.client_wrapper
    if not client_wrapper or not client_wrapper.is_connected:
        return {"chats": [], "error": "Cliente Telegram não conectado"}
        
    chat_service = ChatService(client_wrapper.client)
    media_cache = MediaCache(client_wrapper.client)
    
    chats = await chat_service.get_all_chats()
    
    results = []
    uncached = []
    for c in chats:
        avatar_url = None
        if media_cache.has_cached(c.id):
            avatar_url = f"/api/avatar/{c.id}"
        else:
            uncached.append(c.id)
            
        results.append({
            "id": c.id,
            "title": c.title,
            "chat_type": c.chat_type,
            "username": c.username,
            "participants": c.participants_count,
            "is_public": c.is_public,
            "avatar": avatar_url
        })
        
    if uncached:
        asyncio.create_task(media_cache.get_avatars_batch(uncached[:50]))
        
    return {"chats": results}

@chats_router.get("/chats/{chat_id}/messages", dependencies=[Depends(get_current_user)])
async def get_chat_messages(chat_id: int, request: Request, limit: int = 50, offset_id: int = 0, around_id: int = 0):
    client_wrapper = request.app.state.client_wrapper
    if not client_wrapper or not client_wrapper.is_connected:
        return {"messages": [], "error": "Cliente Telegram não conectado"}

    client = client_wrapper.client
    messages = []
    try:
        kwargs = {"limit": limit}
        if offset_id > 0:
            kwargs["offset_id"] = offset_id
        if around_id > 0:
            # Puxa metade antes, metade depois para centralizar no checkpoint
            kwargs["limit"] = limit
            kwargs["offset_id"] = around_id + (limit // 2)

        async for msg in client.iter_messages(chat_id, **kwargs):
            if not msg.text and not msg.media and not getattr(msg, 'action', None):
                continue

            media_type = None
            if msg.media:
                media_type = msg.media.__class__.__name__

            messages.append({
                "id": msg.id,
                "text": msg.text[:200] + "..." if msg.text and len(msg.text) > 200 else msg.text,
                "date": msg.date.isoformat() if msg.date else None,
                "media_type": media_type,
                "grouped_id": msg.grouped_id
            })
    except Exception as e:
        return {"error": str(e), "messages": []}

    return {"messages": messages}

@chats_router.get("/avatar/{chat_id}")
async def get_avatar(chat_id: str, request: Request):
    try:
        chat_id_int = int(chat_id)
        cache_path = Path(f"data/cache/avatars/{chat_id_int}.jpg")
        if cache_path.exists():
            return FileResponse(str(cache_path))
    except ValueError:
        pass

    # Importante: Como não tem mais a foto no frontend, usemos clonei.png ou icon.ico do folder de assets
    import sys
    if getattr(sys, 'frozen', False):
        assets_dir = Path(sys._MEIPASS) / "assets"
    else:
        assets_dir = Path(__file__).parent.parent.parent / "assets"
    fallback_path = assets_dir / "icon.ico"
    if fallback_path.exists():
        return FileResponse(str(fallback_path))
    return FileResponse("frontend/placeholder.png")  # fallback do fallback

@chats_router.get("/failed-logs/{checkpoint_id}", dependencies=[Depends(get_current_user)])
async def get_failed_logs(checkpoint_id: int, request: Request):
    db = request.app.state.db
    repo = FailedMessagesRepository(db)
    fails = await repo.get_pending_by_checkpoint(checkpoint_id)
    return {"failed_messages": [f.model_dump() for f in fails]}
