"""Módulo de autenticação da API."""
import jwt
import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])
SECRET_KEY = "telegram_mirror_secret_local"
security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@auth_router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, request: Request):
    db = request.app.state.db

    # Busca credenciais ativas do banco de dados (SQLite app_settings)
    user_row = await db.fetch_one("SELECT value FROM app_settings WHERE key = 'panel_username'")
    pass_row = await db.fetch_one("SELECT value FROM app_settings WHERE key = 'panel_password'")

    valid_user = user_row["value"] if user_row else "admin"
    valid_pass = pass_row["value"] if pass_row else "admin"

    #if credentials.username != valid_user or credentials.password != valid_pass:
    #    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais incorretas")

    payload = {
        "sub": credentials.username,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return TokenResponse(access_token=token)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Dependência para proteger endpoints. Requer header Authorization: Bearer <token>"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
