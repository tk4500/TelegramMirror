from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from src.web.auth import get_current_user
from src.utils.logger import logger
from telethon import TelegramClient

tg_auth_router = APIRouter(prefix="/api/tg-auth", tags=["Telegram Auth"], dependencies=[Depends(get_current_user)])

class PhoneRequest(BaseModel):
    account_number: int
    phone: str
    api_id: int
    api_hash: str

class CodeRequest(BaseModel):
    account_number: int
    phone: str
    phone_code_hash: str
    code: str
    api_id: int
    api_hash: str

class PasswordRequest(BaseModel):
    account_number: int
    password: str

@tg_auth_router.post("/send-code")
async def send_code(payload: PhoneRequest, request: Request):
    session_manager = request.app.state.client_wrapper._session_manager
    try:
        # Tenta buscar um client ativo, mas se as chaves da UI forem diferentes ou for a hora de logar de fato,
        # O mais seguro para evitar cache quebrado é forçar a recriação do cliente se não houver conexão autorizada
        client = session_manager.get_client(payload.account_number)

        # Se existir mas estiver desconectado/quebrado, remove do cache para instanciar com o novo api_id/hash
        if client and not client.is_connected():
            session_manager.remove_client(payload.account_number)
            client = None

        if not client:
            client = session_manager.create_client(payload.account_number, api_id=payload.api_id, api_hash=payload.api_hash)

        # O Telethon armazena as chaves no banco SQLite por IP. Se estivermos num servidor de testes,
        # e conectarmos, ele detecta que a auth request bate no DC errado.
        # Se for o caso, disconnectamos o client antigo se existir.
        if not client.is_connected():
            await client.connect()

        # Guarda no state para os proximos requests as credenciais
        if not hasattr(request.app.state, 'auth_flows'):
            request.app.state.auth_flows = {}
        request.app.state.auth_flows[payload.account_number] = {
            "api_id": payload.api_id,
            "api_hash": payload.api_hash
        }

        # Telethon as vezes lida automaticamente com PhoneMigrateError se o numero bater no DC errado.
        # Caso nao, ele solta excecao e avisamos para recriar/apagar cache.
        result = await client.send_code_request(payload.phone)
        return {"phone_code_hash": result.phone_code_hash, "message": "Código enviado."}
    except Exception as e:
        logger.error("Erro ao enviar código para %s: %s", payload.phone, e)
        raise HTTPException(status_code=400, detail=f"Erro ao enviar código: {e}")
        if "DC 2" in str(e) or "PhoneMigrateError" in str(e):
            # Deleta session corrompida / com DC errado
            await session_manager.disconnect_client(payload.account_number)
            import os
            try:
                os.remove(session_manager._get_session_path(payload.account_number) + ".session")
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="Ambiente (Test/Prod) inconsistente com o número. O cache foi limpo. Salve as configs e tente conectar novamente.")
        raise HTTPException(status_code=400, detail=str(e))

@tg_auth_router.post("/login")
async def login(payload: CodeRequest, request: Request):
    session_manager = request.app.state.client_wrapper._session_manager
    try:
        client = session_manager.get_client(payload.account_number)
        await client.sign_in(phone=payload.phone, code=payload.code, phone_code_hash=payload.phone_code_hash)
        
        # Atualiza a conta ativa e is_initialized no client_wrapper
        cw = request.app.state.client_wrapper
        cw._active_account = payload.account_number
        cw._is_initialized = True

        # Garante que criamos o registro da conta no banco de dados para listar depois
        from src.db.repositories.accounts_repo import AccountsRepository
        from src.db.models import Account, AccountStatus
        repo = AccountsRepository(request.app.state.db)

        acc_db = await repo.get_by_id(payload.account_number)
        if acc_db:
            await request.app.state.db.execute("UPDATE accounts SET phone = ?, api_id = ?, api_hash = ?, status = 'connected' WHERE id = ?", (payload.phone, payload.api_id, payload.api_hash, payload.account_number))
        else:
            acc = Account(
                id=payload.account_number, phone=payload.phone,
                api_id=payload.api_id, api_hash=payload.api_hash,
                is_primary=(payload.account_number == 1), status=AccountStatus.CONNECTED
            )
            await repo.create(acc)


        return {"message": "Autenticado com sucesso", "status": "authorized"}
    except Exception as e:
        if "password" in str(e).lower() or "SessionPasswordNeededError" in str(e):
            return {"message": "2FA required", "status": "2fa_required"}
        logger.error("Erro no login da conta %d: %s", payload.account_number, e)
        raise HTTPException(status_code=400, detail=str(e))

@tg_auth_router.post("/login/2fa")
async def login_2fa(payload: PasswordRequest, request: Request):
    session_manager = request.app.state.client_wrapper._session_manager
    try:
        client = session_manager.get_client(payload.account_number)
        await client.sign_in(password=payload.password)
        
        # Atualiza a conta ativa e is_initialized no client_wrapper
        cw = request.app.state.client_wrapper
        cw._active_account = payload.account_number
        cw._is_initialized = True

        # Garante que criamos o registro da conta no banco de dados para listar depois
        from src.db.repositories.accounts_repo import AccountsRepository
        from src.db.models import Account, AccountStatus
        repo = AccountsRepository(request.app.state.db)


        acc_db = await repo.get_by_id(payload.account_number)
        if acc_db:
            await request.app.state.db.execute("UPDATE accounts SET status = 'connected' WHERE id = ?", (payload.account_number,))
        else:
            acc = Account(
                id=payload.account_number, phone=client._phone if hasattr(client, '_phone') else "",
                api_id=client.api_id, api_hash=client.api_hash,
                is_primary=(payload.account_number == 1), status=AccountStatus.CONNECTED
            )
            await repo.create(acc)

        return {"message": "Autenticado com sucesso via 2FA", "status": "authorized"}
    except Exception as e:
        logger.error("Erro no login 2FA da conta %d: %s", payload.account_number, e)
        raise HTTPException(status_code=400, detail=str(e))
