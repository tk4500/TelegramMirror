import threading
import webbrowser
import uvicorn
import pystray
import asyncio
import os
import sys
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import ctypes

# Ocultar o console explicitamente no Windows (garantia extra)
if sys.platform == "win32":
    kernel32 = ctypes.WinDLL('kernel32')
    user32 = ctypes.WinDLL('user32')
    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)

# Adiciona a raiz do projeto ao PYTHONPATH para resolver importacoes de 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.web.app import app
from src.core.config import AppConfig

class DesktopApp:
    def __init__(self):
        self.server = None
        self.server_thread = None
        self.icon = None

    def create_icon_image(self):
        width = 64
        height = 64
        color1 = (42, 171, 238)  # Telegram Blue
        color2 = (255, 255, 255) # White
        
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            (width // 4, height // 4, width - width // 4, height - height // 4),
            fill=color2
        )
        return image

    def start_server(self):
        config_app = AppConfig()
        log_level = "debug" if config_app.debug_mode else "info"
        config = uvicorn.Config(app, host="127.0.0.1", port=8080, log_level=log_level, log_config=None)
        self.server = uvicorn.Server(config)
        self.server.run()

    def open_panel(self, icon, item):
        webbrowser.open("http://127.0.0.1:8080")

    def exit_app(self, icon, item):
        if self.server:
            self.server.should_exit = True
        icon.stop()
        # Forca saida rapida ja que threads as vezes travam o loop
        os._exit(0)

    def run(self):
        # O StartupManager agora é gerenciado pelo lifespan event no FastAPI (src/web/app.py)
        # O FastAPI se encarregará de executar os setups na mesma thread e loop que as rotas

        # Inicia a API no background
        self.server_thread = threading.Thread(target=self.start_server, daemon=True)
        self.server_thread.start()

        # Abre no browser padrao
        webbrowser.open("http://127.0.0.1:8080")

        # Cria o icone da System Tray
        menu = pystray.Menu(
            item('Abrir Painel', self.open_panel, default=True),
            item('Sair', self.exit_app)
        )

        try:
            # Puxa o icone da nova pasta centralizada assets
            icon_img = Image.open(os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(__file__) + '/..'), "assets", "icon.ico"))
        except Exception:
            icon_img = self.create_icon_image()

        self.icon = pystray.Icon(
            "TelegramMirror",
            icon_img,
            "Telegram Mirror",
            menu
        )
        self.icon.run()

if __name__ == "__main__":
    DesktopApp().run()
