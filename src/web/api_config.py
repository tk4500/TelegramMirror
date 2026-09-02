"""Endpoints de configuração (Regex e Perfis)."""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from src.web.auth import get_current_user
from src.db.models import RuleType, SpeedProfile

config_router = APIRouter(prefix="/api/config", tags=["Config"], dependencies=[Depends(get_current_user)])

class RuleCreate(BaseModel):
    old_value: str
    new_value: str = ""
    rule_type: str
    account_id: int | None = None

@config_router.get("/regex-rules")
async def get_rules(request: Request):
    db = request.app.state.db
    rows = await db.fetch_all("SELECT * FROM replacement_rules WHERE is_active = 1 ORDER BY id DESC")
    return {"rules": rows}

@config_router.post("/regex-rules")
async def create_rule(rule: RuleCreate, request: Request):
    db = request.app.state.db
    try:
        r_type = RuleType(rule.rule_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid rule_type")

    cursor = await db.execute(
        "INSERT INTO replacement_rules (old_value, new_value, rule_type, account_id) VALUES (?, ?, ?, ?)",
        (rule.old_value, rule.new_value, r_type.value, rule.account_id)
    )
    return {"id": cursor.lastrowid, "message": "Regra criada"}

@config_router.delete("/regex-rules/{rule_id}")
async def delete_rule(rule_id: int, request: Request):
    db = request.app.state.db
    await db.execute("UPDATE replacement_rules SET is_active = 0 WHERE id = ?", (rule_id,))
    return {"message": "Regra removida"}

@config_router.get("/speed-profiles")
async def get_speed_profiles():
    return {"profiles": [{"id": p.value, "name": p.name} for p in SpeedProfile]}

class AppSettings(BaseModel):
    panel_username: str | None = None
    panel_password: str | None = None

@config_router.get("/app-settings")
async def get_app_settings(request: Request):
    db = request.app.state.db
    rows = await db.fetch_all("SELECT * FROM app_settings")
    settings = {r["key"]: r["value"] for r in rows}

    return {
        "panel_username": settings.get("panel_username", "admin"),
        # Senha vazia para nao transitar texto puro de volta
        "panel_password": "",
        "debug_mode": getattr(request.app.state, "config", None).debug_mode if hasattr(request.app.state, "config") else False
    }

@config_router.post("/app-settings")
async def save_app_settings(settings: AppSettings, request: Request):
    db = request.app.state.db

    # Configs do Painel Web (Se fornecidas, ignora as strings vazias)
    if settings.panel_username and settings.panel_username.strip():
        await db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("panel_username", settings.panel_username.strip()))

    if settings.panel_password and settings.panel_password.strip():
        await db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", ("panel_password", settings.panel_password.strip()))

    return {"message": "Configurações salvas"}
