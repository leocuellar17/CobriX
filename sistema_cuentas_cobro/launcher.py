"""Lanzador de escritorio sin consola: instancia única, respaldo automático, Uvicorn y System Tray."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from PIL import Image, ImageDraw
import pystray
import uvicorn

from app.api.routes import register_shutdown_callback
from app.core.config import settings
from app.db.database import Base, engine
from app.main import app
from app.models import domain  # noqa: F401
from app.services.backup_service import crear_respaldo_seguro


APP_URL = f"http://{settings.HOST}:{settings.PORT}"
HEALTH_URL = f"{APP_URL}{settings.API_V1_PREFIX}/health"


def configurar_logging() -> logging.Logger:
    """Redirige los logs a un archivo rotativo para evitar fallos cuando no hay consola."""
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = settings.LOGS_DIR / "app.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    return logging.getLogger("cobrix.launcher")


def servidor_activo() -> bool:
    """Verifica si ya existe una instancia respondiendo HTTP 200 en /api/v1/health."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def abrir_navegador_app(url: str = APP_URL) -> None:
    """Intenta abrir en modo ventana nativa (--app) con Edge/Chrome o usa el navegador por defecto."""
    if platform.system() == "Windows":
        candidatos = [
            Path(os.environ.get("PROGRAMFILES(X86)", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ]
        for exe in candidatos:
            if exe.is_file():
                try:
                    subprocess.Popen([str(exe), f"--app={url}"])
                    return
                except OSError:
                    continue

        for cmd in ("msedge", "chrome"):
            encontrado = shutil.which(cmd)
            if encontrado:
                try:
                    subprocess.Popen([encontrado, f"--app={url}"])
                    return
                except OSError:
                    continue

    webbrowser.open(url)


def cargar_icono_bandeja() -> Image.Image:
    """Carga assets/icono.ico o genera un ícono de respaldo en memoria."""
    icono_path = settings.BUNDLE_DIR / "assets" / "icono.ico"
    if icono_path.is_file():
        return Image.open(icono_path)

    img = Image.new("RGBA", (64, 64), (0, 120, 212, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(4, 4), (60, 60)], radius=14, fill=(0, 120, 212, 255))
    return img


def abrir_carpeta_pdfs() -> None:
    """Abre la carpeta de PDFs generados en el explorador del sistema operativo."""
    settings.OUTPUT_PDF_DIR.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        os.startfile(str(settings.OUTPUT_PDF_DIR))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(settings.OUTPUT_PDF_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(settings.OUTPUT_PDF_DIR)])


def main() -> None:
    logger = configurar_logging()
    logger.info("Iniciando lanzador de Cuentas de Cobro (CobriX)...")

    if servidor_activo():
        logger.info("Instancia previa detectada en %s. Abriendo navegador.", APP_URL)
        abrir_navegador_app(APP_URL)
        sys.exit(0)

    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    if settings.DB_PATH.is_file():
        try:
            crear_respaldo_seguro()
        except Exception as exc:
            logger.exception("Error al crear respaldo inicial: %s", exc)

    config = uvicorn.Config(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_config=None,
    )
    server = uvicorn.Server(config)

    hilo_servidor = threading.Thread(target=server.run, daemon=True)
    hilo_servidor.start()

    # Espera activa hasta 10 segundos a que /api/v1/health responda 200 OK
    inicio = time.monotonic()
    listo = False
    while time.monotonic() - inicio < 10.0:
        if servidor_activo():
            listo = True
            break
        time.sleep(0.2)

    if listo:
        logger.info("Servidor listo en %s. Abriendo interfaz.", APP_URL)
        abrir_navegador_app(APP_URL)
    else:
        logger.error("El servidor no respondió dentro del tiempo esperado.")

    tray_icon_ref: dict[str, pystray.Icon | None] = {"icon": None}

    def detener_todo() -> None:
        logger.info("Ejecutando cierre limpio y respaldo final...")
        try:
            if settings.DB_PATH.is_file():
                crear_respaldo_seguro()
        except Exception as exc:
            logger.exception("Error en respaldo final: %s", exc)
        server.should_exit = True
        if tray_icon_ref["icon"] is not None:
            tray_icon_ref["icon"].stop()

    register_shutdown_callback(detener_todo)

    def on_abrir(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        abrir_navegador_app(APP_URL)

    def on_carpeta(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        abrir_carpeta_pdfs()

    def on_backup(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        try:
            crear_respaldo_seguro()
        except Exception as exc:
            logger.exception("Error creando respaldo manual desde bandeja: %s", exc)

    def on_salir(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        detener_todo()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Cuentas de Cobro", on_abrir, default=True),
        pystray.MenuItem("Abrir Carpeta de PDFs", on_carpeta),
        pystray.MenuItem("Hacer Copia de Seguridad Ahora", on_backup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Cerrar Programa", on_salir),
    )

    tray_icon = pystray.Icon(
        "CobriX",
        cargar_icono_bandeja(),
        "Cuentas de Cobro",
        menu,
    )
    tray_icon_ref["icon"] = tray_icon
    tray_icon.run()


if __name__ == "__main__":
    main()
