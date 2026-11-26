"""Fixtures globales de pytest: BD SQLite en memoria, PDFService temporal y TestClient."""

from collections.abc import Generator
import os
from pathlib import Path
import tempfile
from typing import Any

# Aislar COBRIX_DATA_DIR antes de importar app.* para no tocar Documentos del usuario
_TEST_DATA_DIR = Path(tempfile.gettempdir()) / "cobrix_pytest_data"
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("COBRIX_DATA_DIR", str(_TEST_DATA_DIR))

from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import cobros_service  # noqa: E402
from app.services.pdf_service import PDFService  # noqa: E402


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provee una sesión SQLite en memoria aislada por cada prueba."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn: Any, _conn_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=Session,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def isolated_pdf_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PDFService:
    """Redirige la salida de PDFs y assets de pruebas a un directorio temporal."""
    temp_pdf = PDFService(
        templates_dir=settings.TEMPLATES_DIR,
        output_dir=tmp_path / "PDFs_Generados",
        assets_dir=tmp_path / "archivos" / "assets",
    )
    monkeypatch.setattr(cobros_service, "pdf_service", temp_pdf)
    return temp_pdf


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provee un TestClient de FastAPI conectado a la sesión SQLite en memoria."""
    cobros_service.seed_emisor_por_defecto(db_session)

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
