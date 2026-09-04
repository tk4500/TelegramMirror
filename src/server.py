import uvicorn
import os
import sys

# Adiciona a raiz do projeto ao PYTHONPATH para resolver importacoes de 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.web.app import app
from src.core.config import AppConfig

def start_headless_server():
    print("Iniciando servidor em modo headless (sem interface gráfica)...")
    config_app = AppConfig()
    log_level = "debug" if config_app.debug_mode else "info"
    
    # Rodando em 0.0.0.0 para que a API/Painel possa ser acessada remotamente da VPS
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level=log_level)

if __name__ == "__main__":
    start_headless_server()
