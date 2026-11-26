"""Endpoints RESTful organizados por dominio bajo el prefijo /api/v1."""

from collections.abc import Callable
from typing import Annotated, Literal, Optional
import os
import signal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.schemas.schemas import (
    AnularCuentaRequest,
    ClienteCreate,
    ClienteEstadoUpdate,
    ClienteResponse,
    ClienteUpdate,
    CrearCobroManualSchema,
    CuentaCobroResponse,
    EmitirCuentaSchema,
    EmisorResponse,
    EmisorUpdate,
    IniciarMesRequest,
    IniciarMesResponse,
    PagoCuentaRequest,
    TableroMensualResponse,
)
from app.services import backup_service, cobros_service


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/v1")

_shutdown_callback: Optional[Callable[[], None]] = None


def register_shutdown_callback(callback: Callable[[], None]) -> None:
    """Registra el callback del lanzador para detener Uvicorn y pystray limpiamente."""
    global _shutdown_callback
    _shutdown_callback = callback


def _ejecutar_apagado() -> None:
    """Detiene el servidor registrado o envía SIGTERM al proceso actual."""
    if _shutdown_callback is not None:
        _shutdown_callback()
    else:
        os.kill(os.getpid(), signal.SIGTERM)


# ---------------------------------------------------------------------------
# Emisor
# ---------------------------------------------------------------------------


@router.get(
    "/emisor",
    response_model=EmisorResponse,
    tags=["Emisor"],
    summary="Obtener perfil del emisor",
    description="Retorna el perfil único (id=1) del profesional independiente emisor.",
)
def get_emisor(db: DbSession) -> EmisorResponse:
    return cobros_service.obtener_emisor(db)


@router.put(
    "/emisor",
    response_model=EmisorResponse,
    tags=["Emisor"],
    summary="Actualizar perfil del emisor",
    description="Actualiza los datos tributarios, bancarios y notas legales del emisor.",
)
def update_emisor(datos: EmisorUpdate, db: DbSession) -> EmisorResponse:
    return cobros_service.actualizar_emisor(db, datos)


@router.post(
    "/emisor/archivos/{tipo}",
    response_model=EmisorResponse,
    tags=["Emisor"],
    summary="Subir firma o anexo PDF del emisor",
    description=(
        "Sube la firma digitalizada (.png/.jpg/.jpeg) o anexos PDF (rut, cert_bancaria) "
        "y actualiza la ruta en el perfil del emisor."
    ),
)
def upload_archivo_emisor(
    tipo: Literal["firma", "rut", "cert_bancaria"],
    db: DbSession,
    file: UploadFile = File(...),
) -> EmisorResponse:
    return cobros_service.actualizar_archivo_emisor(db, tipo, file)


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


@router.get(
    "/clientes",
    response_model=list[ClienteResponse],
    tags=["Clientes"],
    summary="Listar clientes",
    description="Lista los clientes registrados con filtro opcional por estado activo y búsqueda por nombre o NIT.",
)
def list_clientes(
    db: DbSession,
    solo_activos: bool = Query(
        default=True,
        description="Si es true, retorna únicamente clientes activos.",
    ),
    busqueda: Optional[str] = Query(
        default=None,
        description="Texto parcial para filtrar por razón social o documento/NIT.",
    ),
) -> list[ClienteResponse]:
    return cobros_service.listar_clientes(
        db,
        solo_activos=solo_activos,
        busqueda=busqueda,
    )


@router.post(
    "/clientes",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Clientes"],
    summary="Crear cliente",
    description="Registra un nuevo cliente (persona natural o jurídica) validando unicidad de documento/NIT.",
)
def create_cliente(datos: ClienteCreate, db: DbSession) -> ClienteResponse:
    return cobros_service.crear_cliente(db, datos)


@router.put(
    "/clientes/{cliente_id}",
    response_model=ClienteResponse,
    tags=["Clientes"],
    summary="Actualizar cliente",
    description="Actualiza los datos de un cliente existente.",
)
def update_cliente(
    cliente_id: int,
    datos: ClienteUpdate,
    db: DbSession,
) -> ClienteResponse:
    return cobros_service.actualizar_cliente(db, cliente_id, datos)


@router.patch(
    "/clientes/{cliente_id}/estado",
    response_model=ClienteResponse,
    tags=["Clientes"],
    summary="Activar o desactivar cliente",
    description="Realiza soft delete o reactivación de un cliente.",
)
def patch_estado_cliente(
    cliente_id: int,
    datos: ClienteEstadoUpdate,
    db: DbSession,
) -> ClienteResponse:
    return cobros_service.cambiar_estado_cliente(db, cliente_id, datos.activo)


# ---------------------------------------------------------------------------
# Cuentas de Cobro y Tablero
# ---------------------------------------------------------------------------


@router.get(
    "/tablero/{periodo_mes}",
    response_model=TableroMensualResponse,
    tags=["Tablero y Cartera"],
    summary="Obtener tablero mensual y cartera vencida",
    description=(
        "Retorna las cuentas del mes ordenadas estilo To-Do List, "
        "la cartera vencida de meses anteriores y los KPIs financieros."
    ),
)
def get_tablero_mensual(periodo_mes: str, db: DbSession) -> TableroMensualResponse:
    return cobros_service.obtener_tablero_mensual(db, periodo_mes)


@router.post(
    "/cuentas/iniciar-mes",
    response_model=IniciarMesResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Cuentas de Cobro"],
    summary="Iniciar apertura autónoma de mes",
    description=(
        "Genera cuentas en estado BORRADOR de forma idempotente para todos los "
        "clientes activos y recurrentes en el periodo indicado."
    ),
)
def iniciar_mes(datos: IniciarMesRequest, db: DbSession) -> IniciarMesResponse:
    return cobros_service.generar_pendientes_mes(db, datos.periodo_mes)


@router.post(
    "/cuentas/manual",
    response_model=CuentaCobroResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Cuentas de Cobro"],
    summary="Crear cobro manual extraordinario",
    description="Permite crear una cuenta de cobro puntual en estado BORRADOR o EMITIDA.",
)
def create_cobro_manual(
    datos: CrearCobroManualSchema,
    db: DbSession,
) -> CuentaCobroResponse:
    return cobros_service.crear_cobro_manual(db, datos)


@router.put(
    "/cuentas/{cuenta_id}/emitir",
    response_model=CuentaCobroResponse,
    tags=["Cuentas de Cobro"],
    summary="Redactar y emitir cuenta de cobro",
    description=(
        "Guarda honorarios, valor y fecha de emisión, asigna consecutivo secuencial "
        "del año (CC-YYYY-NNNN) si no tiene, y cambia el estado a EMITIDA."
    ),
)
def emitir_cuenta(
    cuenta_id: int,
    datos: EmitirCuentaSchema,
    db: DbSession,
) -> CuentaCobroResponse:
    return cobros_service.emitir_cuenta_cobro(db, cuenta_id, datos)


@router.patch(
    "/cuentas/{cuenta_id}/pago",
    response_model=CuentaCobroResponse,
    tags=["Cuentas de Cobro"],
    summary="Marcar o revertir pago de cuenta",
    description="Marca una cuenta EMITIDA como PAGADA o revierte una PAGADA a EMITIDA.",
)
def patch_pago_cuenta(
    cuenta_id: int,
    datos: PagoCuentaRequest,
    db: DbSession,
) -> CuentaCobroResponse:
    return cobros_service.cambiar_estado_pago(
        db,
        cuenta_id=cuenta_id,
        pagada=datos.pagada,
        fecha_pago=datos.fecha_pago,
    )


@router.patch(
    "/cuentas/{cuenta_id}/anular",
    response_model=CuentaCobroResponse,
    tags=["Cuentas de Cobro"],
    summary="Anular cuenta de cobro",
    description="Cambia el estado a ANULADA conservando su consecutivo para auditoría.",
)
def patch_anular_cuenta(
    cuenta_id: int,
    db: DbSession,
    datos: Optional[AnularCuentaRequest] = Body(default=None),
) -> CuentaCobroResponse:
    observaciones = datos.observaciones_internas if datos is not None else None
    return cobros_service.anular_cuenta_cobro(
        db,
        cuenta_id=cuenta_id,
        observaciones_internas=observaciones,
    )


@router.delete(
    "/cuentas/{cuenta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Cuentas de Cobro"],
    summary="Eliminar borrador de cuenta",
    description="Elimina físicamente una cuenta de cobro únicamente si está en estado BORRADOR.",
)
def delete_cuenta_borrador(cuenta_id: int, db: DbSession) -> Response:
    cobros_service.eliminar_cuenta_borrador(db, cuenta_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/cuentas/{cuenta_id}/pdf",
    tags=["Cuentas de Cobro"],
    summary="Descargar o visualizar PDF de la cuenta de cobro",
    description=(
        "Retorna el PDF de la cuenta de cobro. Si no existe en disco o regenerar=true, "
        "lo genera al vuelo con o sin anexos."
    ),
)
def get_cuenta_pdf(
    cuenta_id: int,
    db: DbSession,
    incluir_anexos: bool = Query(
        default=True,
        description="Si es true, fusiona RUT y Certificación Bancaria al final del PDF.",
    ),
    regenerar: bool = Query(
        default=False,
        description="Si es true, fuerza la regeneración del PDF en disco.",
    ),
) -> FileResponse:
    ruta_pdf = cobros_service.obtener_o_generar_pdf(
        db,
        cuenta_id=cuenta_id,
        incluir_anexos=incluir_anexos,
        regenerar=regenerar,
    )
    return FileResponse(
        path=str(ruta_pdf),
        media_type="application/pdf",
        filename=ruta_pdf.name,
    )


@router.post(
    "/sistema/abrir-carpeta/{periodo_mes}",
    tags=["Sistema"],
    summary="Abrir carpeta mensual de PDFs en el explorador local",
    description="Crea si no existe y abre la carpeta PDFs_Generados/{YYYY}/{MM}_{Mes}.",
)
def post_abrir_carpeta_periodo(periodo_mes: str) -> dict[str, object]:
    carpeta = cobros_service.abrir_carpeta_periodo(periodo_mes)
    return {
        "periodo_mes": periodo_mes,
        "ruta": str(carpeta),
        "abierta": True,
    }


@router.get(
    "/health",
    tags=["Sistema"],
    summary="Verificación de salud de la API",
    description="Endpoint usado por el lanzador de escritorio para confirmar disponibilidad.",
)
def api_health_check() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@router.post(
    "/sistema/backup",
    tags=["Sistema"],
    summary="Crear respaldo manual inmediato de la base de datos",
    description="Genera una copia transaccional segura de cobros.db en la carpeta de respaldos.",
)
def post_crear_respaldo() -> dict[str, str]:
    ruta_backup = backup_service.crear_respaldo_seguro()
    return {
        "status": "ok",
        "archivo": ruta_backup.name,
        "ruta": str(ruta_backup),
    }


@router.post(
    "/sistema/apagar",
    tags=["Sistema"],
    summary="Respaldar y apagar el servidor local",
    description="Ejecuta un respaldo final de SQLite y detiene el proceso limpiamente.",
)
def post_apagar_sistema(background_tasks: BackgroundTasks) -> dict[str, str]:
    if settings.DB_PATH.is_file():
        backup_service.crear_respaldo_seguro()
    background_tasks.add_task(_ejecutar_apagado)
    return {
        "status": "shutting_down",
        "mensaje": "Respaldo completado. Cerrando aplicación...",
    }
