from fastapi import APIRouter, Depends, Request
from src.web.auth import get_current_user
from pathlib import Path
import os
import re

logs_router = APIRouter(prefix="/api/logs", tags=["Logs"], dependencies=[Depends(get_current_user)])

# Regex para parsear logs no formato: 2026-08-24 16:56:37 - telegram_mirror - INFO - === Iniciando TelegramMirror ===
LOG_PATTERN = re.compile(r'^(?P<time>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+-\s+.*?\s+-\s+(?P<level>[A-Z]+)\s+-\s+(?P<event>.*)$')

@logs_router.get("/recent")
async def get_recent_logs(lines: int = 100):
    log_file = Path("logs/telegram_mirror.log")
    if not log_file.exists():
        return {"logs": [{"time": "-", "level": "INFO", "event": "Arquivo de log ainda não gerado."}]}

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        parsed_logs = []
        for line in reversed(all_lines):
            if not line.strip():
                continue

            match = LOG_PATTERN.match(line)
            if match:
                # Converter timezone/data para hora local simplificada se desejar, mas enviando a string bruta é ok
                time_str = match.group('time')
                level_str = match.group('level')

                # Mapear levels do Python para o frontend CloneX se necessario
                if level_str == "INFO":
                    if "sucesso" in line.lower() or "pronto" in line.lower():
                        level_str = "OK"
                elif level_str == "WARNING":
                    level_str = "WARN"
                elif level_str == "CRITICAL":
                    level_str = "ERROR"

                parsed_logs.append({
                    "time": time_str.split(' ')[1], # So a hora
                    "level": level_str,
                    "event": match.group('event')
                })
            else:
                # Se não der match na regex (ex: traceback ou print puro), acopla ou cria um generico
                if len(parsed_logs) > 0:
                    parsed_logs[-1]["event"] += f" | {line.strip()}"
                else:
                    parsed_logs.append({
                        "time": "-",
                        "level": "ERROR",
                        "event": line.strip()
                    })

            if len(parsed_logs) >= lines:
                break

        return {"logs": parsed_logs}
    except Exception as e:
        return {"logs": [{"time": "-", "level": "ERROR", "event": f"Erro ao ler log: {e}"}]}