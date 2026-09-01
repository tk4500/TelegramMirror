"""
Módulo de logger do sistema.
Configura logging com formatação padrão, saída no console e arquivo rotativo.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import json
import datetime
import functools
import inspect
from typing import Callable, Any

class TelethonEncoder(json.JSONEncoder):
    """Codificador de JSON customizado para tratar datetime e bytes da API do Telegram"""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.hex()
        if hasattr(obj, 'to_dict') and callable(obj.to_dict):
            return obj.to_dict()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def setup_logger(name: str, level: int = None) -> logging.Logger:
    """
    Configura e retorna um logger com o nome e nível especificados.
    """
    if level is None:
        from src.core.config import AppConfig
        level = logging.DEBUG if AppConfig().debug_mode else logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Se já tem handlers, não adiciona novamente
    if logger.handlers:
        return logger

    # Formatação
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (rotativo, max 5MB, mantém 3 backups)
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler(
        'logs/telegram_mirror.log',
        maxBytes=5*1024*1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Logger principal da aplicação
logger = setup_logger('telegram_mirror')

async def ws_log(message: str, level: str = "INFO", details: dict = None):
    """
    Envia log para o frontend via WebSocket, com suporte opcional a detalhes em JSON (Modo Debug).
    """
    # Importação local para evitar circular imports se ws_manager for carregado antes
    from src.web.ws_manager import ws_manager

    payload = {
        "message": message,
        "level": level.lower()
    }

    if details is not None:
        try:
            # Serializa os detalhes garantindo que não há tipos incompatíveis
            serialized = json.loads(json.dumps(details, cls=TelethonEncoder))
            payload["details"] = serialized
            # Também salva no log em arquivo físico para o usuário
            logger.debug(f"{message} | DETALHES: {json.dumps(serialized, indent=2)}")
        except Exception as e:
            logger.error("Erro ao serializar details para ws_log: %s", e)
            payload["details"] = {"error": "Não foi possível serializar os detalhes."}

    await ws_manager.broadcast("log", payload)


def deep_serialize(obj: Any) -> Any:
    """Tenta serializar o objeto profundamente, sem limites ou truncamentos."""
    try:
        return json.loads(json.dumps(obj, cls=TelethonEncoder))
    except Exception:
        return str(obj)

def log_execution(func: Callable) -> Callable:
    """Decorator para logar a entrada, saída e argumentos de funções em modo debug."""
    if getattr(func, '_is_logged', False):
        return func
        
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        if logger.isEnabledFor(logging.DEBUG):
            file_name = inspect.getsourcefile(func) or "unknown"
            ser_args = deep_serialize(args)
            ser_kwargs = deep_serialize(kwargs)
            logger.debug(f"[DEBUG_MODE] INICIANDO: {file_name} - {func.__name__}() | Args: {ser_args} | Kwargs: {ser_kwargs}")
        
        try:
            result = await func(*args, **kwargs)
            if logger.isEnabledFor(logging.DEBUG):
                ser_res = deep_serialize(result)
                ret_type = type(result).__name__
                logger.debug(f"[DEBUG_MODE] RETORNO: {func.__name__}() -> {ret_type} | Val: {ser_res}")
            return result
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[DEBUG_MODE] EXCEÇÃO em {func.__name__}(): {type(e).__name__}: {e}")
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        if logger.isEnabledFor(logging.DEBUG):
            file_name = inspect.getsourcefile(func) or "unknown"
            ser_args = deep_serialize(args)
            ser_kwargs = deep_serialize(kwargs)
            logger.debug(f"[DEBUG_MODE] INICIANDO: {file_name} - {func.__name__}() | Args: {ser_args} | Kwargs: {ser_kwargs}")
            
        try:
            result = func(*args, **kwargs)
            if logger.isEnabledFor(logging.DEBUG):
                ser_res = deep_serialize(result)
                ret_type = type(result).__name__
                logger.debug(f"[DEBUG_MODE] RETORNO: {func.__name__}() -> {ret_type} | Val: {ser_res}")
            return result
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[DEBUG_MODE] EXCEÇÃO em {func.__name__}(): {type(e).__name__}: {e}")
            raise
            
    wrapper = async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    wrapper._is_logged = True
    return wrapper

