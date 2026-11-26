"""Servicio de respaldo automático e inmutable para SQLite con política de retención."""

from datetime import datetime
import logging
from pathlib import Path
import sqlite3
from typing import Optional

from app.core.config import settings
from app.core.exceptions import BusinessRuleException


logger = logging.getLogger(__name__)


def rotar_respaldos(backups_dir: Path, max_archivos: int = 30) -> int:
    """Conserva únicamente los últimos `max_archivos` respaldos y elimina los más antiguos."""
    if max_archivos < 1 or not backups_dir.is_dir():
        return 0

    archivos = sorted(
        backups_dir.glob("cobros_backup_*.db"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    eliminados = 0
    for antiguo in archivos[max_archivos:]:
        try:
            antiguo.unlink()
            eliminados += 1
        except OSError as exc:
            logger.warning("No se pudo eliminar el respaldo antiguo '%s': %s", antiguo, exc)

    return eliminados


def crear_respaldo_seguro(
    db_path: Optional[Path] = None,
    backups_dir: Optional[Path] = None,
    max_archivos: int = 30,
) -> Path:
    """Crea una copia transaccional consistente de SQLite usando sqlite3.Connection.backup()."""
    origen_path = db_path or settings.DB_PATH
    destino_dir = backups_dir or settings.BACKUPS_DIR
    destino_dir.mkdir(parents=True, exist_ok=True)

    if not origen_path.is_file():
        raise BusinessRuleException(
            f"No existe base de datos en '{origen_path}' para respaldar."
        )

    marca_tiempo = datetime.now().strftime("%Y-%m-%d_%H-%M")
    destino_path = destino_dir / f"cobros_backup_{marca_tiempo}.db"
    if destino_path.exists():
        marca_precisa = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        destino_path = destino_dir / f"cobros_backup_{marca_precisa}.db"

    origen_conn = sqlite3.connect(str(origen_path), timeout=15.0)
    destino_conn = sqlite3.connect(str(destino_path), timeout=15.0)
    try:
        origen_conn.backup(destino_conn)
    finally:
        destino_conn.close()
        origen_conn.close()

    eliminados = rotar_respaldos(destino_dir, max_archivos=max_archivos)
    logger.info(
        "Respaldo SQLite creado en '%s' (respaldos antiguos eliminados: %d).",
        destino_path,
        eliminados,
    )
    return destino_path
