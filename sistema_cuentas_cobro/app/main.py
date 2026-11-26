"""Punto de entrada de la aplicación FastAPI: Lifespan, CORS, estáticos, UI y rutas API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as api_v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.database import Base, SessionLocal, engine
from app.models import domain  # noqa: F401  # Asegura el registro de modelos en Base.metadata
from app.services.cobros_service import seed_emisor_por_defecto


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Inicializa directorios, tablas SQLite y el perfil semilla del emisor."""
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_emisor_por_defecto(db)
    finally:
        db.close()
    yield


settings.ensure_directories()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(settings.ASSETS_DIR)), name="assets")
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

register_exception_handlers(app)
app.include_router(api_v1_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_frontend(request: Request) -> HTMLResponse:
    """Sirve la interfaz web local de CobriX."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health", tags=["Sistema"], summary="Estado del servidor")
def health_check() -> dict[str, str]:
    """Verifica que la API local está en ejecución."""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
