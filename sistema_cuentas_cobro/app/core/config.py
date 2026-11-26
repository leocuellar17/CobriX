"""Configuración centralizada de rutas (desarrollo y PyInstaller), BD y almacenamiento."""

import os
from pathlib import Path
import sys


def resolve_bundle_dir() -> Path:
    """Retorna la ruta de recursos empaquetados (_MEIPASS) o la raíz del proyecto."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent


def resolve_user_data_dir() -> Path:
    """Retorna la carpeta permanente de datos del usuario en Documentos (o modo portable)."""
    env_override = os.environ.get("COBRIX_DATA_DIR")
    if env_override:
        return Path(env_override)

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "portable.flag").is_file():
            return exe_dir / "Cuentas_de_Cobro_Datos"

    return Path.home() / "Documents" / "Cuentas_de_Cobro"


def resolve_output_pdf_dir() -> Path:
    """Los PDFs van a Descargas salvo que COBRIX_DATA_DIR esté definido (tests/portable)."""
    env_override = os.environ.get("COBRIX_DATA_DIR")
    if env_override:
        return Path(env_override) / "PDFs_Generados"
    return Path.home() / "Downloads" / "CobriX_Cuentas"


BUNDLE_DIR: Path = resolve_bundle_dir()
USER_DATA_DIR: Path = resolve_user_data_dir()

DB_PATH: Path = USER_DATA_DIR / "cobros.db"
DATABASE_PATH: Path = DB_PATH
STORAGE_DIR: Path = USER_DATA_DIR / "archivos"
ASSETS_DIR: Path = STORAGE_DIR / "assets"
OUTPUT_PDF_DIR: Path = resolve_output_pdf_dir()
BACKUPS_DIR: Path = USER_DATA_DIR / "backups"
LOGS_DIR: Path = USER_DATA_DIR / "logs"

TEMPLATES_DIR: Path = BUNDLE_DIR / "app" / "templates"
STATIC_DIR: Path = BUNDLE_DIR / "app" / "static"


class Settings:
    """Configuración general del servidor FastAPI y almacenamiento local."""

    APP_NAME: str = "CobriX - Sistema de Cuentas de Cobro"
    APP_VERSION: str = "2.1.0"
    APP_DESCRIPTION: str = (
        "API local para la gestión autónoma de Cuentas de Cobro, "
        "generación documental PDF, clientes recurrentes y control de cartera en Colombia."
    )
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "127.0.0.1"
    PORT: int = 8765
    BUNDLE_DIR: Path = BUNDLE_DIR
    USER_DATA_DIR: Path = USER_DATA_DIR
    DB_PATH: Path = DB_PATH
    DATABASE_URL: str = f"sqlite:///{DB_PATH.as_posix()}"
    STORAGE_DIR: Path = STORAGE_DIR
    ASSETS_DIR: Path = ASSETS_DIR
    OUTPUT_PDF_DIR: Path = OUTPUT_PDF_DIR
    PDF_OUTPUT_DIR: Path = OUTPUT_PDF_DIR
    BACKUPS_DIR: Path = BACKUPS_DIR
    LOGS_DIR: Path = LOGS_DIR
    TEMPLATES_DIR: Path = TEMPLATES_DIR
    STATIC_DIR: Path = STATIC_DIR
    CORS_ORIGINS: list[str] = [
        "http://localhost",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    def ensure_directories(self) -> None:
        """Crea los directorios permanentes de datos, PDFs, respaldos y logs."""
        self.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_PDF_DIR.mkdir(parents=True, exist_ok=True)
        self.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
