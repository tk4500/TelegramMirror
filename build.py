import PyInstaller.__main__
import os
import shutil

def prepare_env_for_build():
    debug_mode = False

    # Copia o .env atual (da máquina do dev) para um arquivo que será embutido no EXE
    if os.path.exists('.env'):
        shutil.copyfile('.env', '.env.embedded')
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('DEBUG_MODE='):
                    val = line.split('=', 1)[1].strip().lower()
                    if val in ('true', '1', 'yes'):
                        debug_mode = True
    else:
        # Garante que criamos um vazio com as flags caso o .env nem exista
        with open('.env.embedded', 'w', encoding='utf-8') as f:
            f.write("DEBUG_MODE=false\\n")

    return debug_mode

if __name__ == "__main__":
    debug = prepare_env_for_build()

    app_name = "TelegramMirror"
    if debug:
        app_name += "-DEBUG"

    PyInstaller.__main__.run([
        "src/desktop.py",
        f"--name={app_name}",
        "--onefile",
        "--noconsole",
        f"--add-data=frontend{os.pathsep}frontend",
        f"--add-data=src/db/schema.sql{os.pathsep}src/db",
        f"--add-data=assets{os.pathsep}assets",
        f"--add-data=.env.embedded{os.pathsep}.",
        f"--icon=assets/icon.ico",
        "--clean",
        "--noconfirm"
    ])

    # Limpa o arquivo temporário
    if os.path.exists('.env.embedded'):
        os.remove('.env.embedded')
