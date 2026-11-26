"""Lógica de negocio transaccional para Emisor, Clientes, Cuentas de Cobro y Cartera."""

from datetime import date
from decimal import Decimal
import logging
import os
from pathlib import Path
import platform
import subprocess
from typing import Literal, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, DuplicateEntityException
from app.core.utils import validar_periodo_mes
from app.models.domain import Cliente, CuentaCobro, Emisor, EstadoCuenta
from app.repositories.cobros_repository import (
    ClienteRepository,
    CuentaCobroRepository,
    EmisorRepository,
)
from app.schemas.schemas import (
    ClienteCreate,
    ClienteUpdate,
    CrearCobroManualSchema,
    EmitirCuentaSchema,
    EmisorUpdate,
    IniciarMesResponse,
    TableroKPIsResponse,
    TableroMensualResponse,
)
from app.services.pdf_service import pdf_service


logger = logging.getLogger(__name__)

_ORDEN_ESTADO_TABLERO: dict[EstadoCuenta, int] = {
    EstadoCuenta.BORRADOR: 0,
    EstadoCuenta.EMITIDA: 1,
    EstadoCuenta.PAGADA: 2,
    EstadoCuenta.ANULADA: 3,
}


def _validar_periodo_o_400(periodo_mes: str) -> str:
    """Valida el formato YYYY-MM o lanza BusinessRuleException."""
    try:
        return validar_periodo_mes(periodo_mes)
    except ValueError as exc:
        raise BusinessRuleException(str(exc)) from exc


def _limpiar_pdf_huerfano(ruta_anterior: Optional[str], ruta_nueva: Path) -> None:
    """Elimina el PDF anterior si la nueva ruta cambió tras editar fecha o cliente."""
    if not ruta_anterior:
        return
    prev = Path(ruta_anterior)
    if prev != ruta_nueva and prev.is_file():
        try:
            prev.unlink()
        except OSError as exc:
            logger.warning("No se pudo eliminar PDF anterior '%s': %s", prev, exc)


# ---------------------------------------------------------------------------
# Emisor
# ---------------------------------------------------------------------------


def seed_emisor_por_defecto(db: Session) -> Emisor:
    """Crea el registro plantilla del Emisor (id=1) si aún no existe."""
    return EmisorRepository(db).get_or_create_default()


def obtener_emisor(db: Session) -> Emisor:
    """Retorna el perfil único del emisor, creándolo si no existe."""
    return EmisorRepository(db).get_or_create_default()


def actualizar_emisor(db: Session, datos: EmisorUpdate) -> Emisor:
    """Actualiza los datos del perfil único del emisor (id=1)."""
    repo = EmisorRepository(db)
    emisor = repo.get_or_create_default()
    return repo.update(emisor, datos, exclude_unset=False)


def actualizar_archivo_emisor(
    db: Session,
    tipo_archivo: Literal["firma", "rut", "cert_bancaria"],
    file: UploadFile,
) -> Emisor:
    """Guarda un archivo del emisor (firma o anexo PDF) y actualiza su ruta en BD."""
    ruta_guardada = pdf_service.guardar_archivo_emisor(tipo_archivo, file)
    repo = EmisorRepository(db)
    emisor = repo.get_or_create_default()

    mapa_campos = {
        "firma": "ruta_firma",
        "rut": "ruta_rut_pdf",
        "cert_bancaria": "ruta_cert_bancaria_pdf",
    }
    return repo.update(emisor, {mapa_campos[tipo_archivo]: ruta_guardada})


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


def listar_clientes(
    db: Session,
    solo_activos: bool = True,
    busqueda: Optional[str] = None,
) -> list[Cliente]:
    """Lista clientes filtrando opcionalmente por estado activo y texto de búsqueda."""
    return ClienteRepository(db).listar_filtrados(
        solo_activos=solo_activos,
        busqueda=busqueda,
    )


def crear_cliente(db: Session, datos: ClienteCreate) -> Cliente:
    """Registra un nuevo cliente validando unicidad de documento_nit."""
    repo = ClienteRepository(db)
    if repo.get_by_documento(datos.documento_nit) is not None:
        raise DuplicateEntityException("cliente", "documento_nit", datos.documento_nit)
    return repo.create(datos)


def actualizar_cliente(
    db: Session,
    cliente_id: int,
    datos: ClienteUpdate,
) -> Cliente:
    """Actualiza los datos de un cliente existente validando unicidad de documento_nit."""
    repo = ClienteRepository(db)
    cliente = repo.get_or_404(cliente_id, "Cliente")
    cambios = datos.model_dump(exclude_unset=True)

    nuevo_doc = cambios.get("documento_nit")
    if nuevo_doc is not None and nuevo_doc != cliente.documento_nit:
        if repo.get_by_documento(nuevo_doc, exclude_id=cliente_id) is not None:
            raise DuplicateEntityException("cliente", "documento_nit", nuevo_doc)

    return repo.update(cliente, cambios)


def cambiar_estado_cliente(
    db: Session,
    cliente_id: int,
    activo: bool,
) -> Cliente:
    """Activa o desactiva (soft delete) un cliente."""
    repo = ClienteRepository(db)
    cliente = repo.get_or_404(cliente_id, "Cliente")
    return repo.update(cliente, {"activo": activo})


# ---------------------------------------------------------------------------
# Operaciones de Cuentas de Cobro y Cartera
# ---------------------------------------------------------------------------


def generar_pendientes_mes(db: Session, periodo_mes: str) -> IniciarMesResponse:
    """Genera cuentas en BORRADOR para clientes recurrentes activos de forma idempotente."""
    periodo_validado = _validar_periodo_o_400(periodo_mes)

    cliente_repo = ClienteRepository(db)
    cuenta_repo = CuentaCobroRepository(db)

    clientes_recurrentes = cliente_repo.listar_recurrentes_activos()
    existentes_ids = cuenta_repo.get_clientes_con_cuenta_en_periodo(periodo_validado)

    creadas = 0
    ya_existentes = 0

    for cliente in clientes_recurrentes:
        if cliente.id in existentes_ids:
            ya_existentes += 1
            continue

        cuenta_repo.create(
            {
                "consecutivo": None,
                "cliente_id": cliente.id,
                "periodo_mes": periodo_validado,
                "fecha_emision": None,
                "concepto_honorarios": None,
                "valor_total": Decimal("0.00"),
                "estado": EstadoCuenta.BORRADOR,
            },
            commit=False,
        )
        creadas += 1

    db.commit()
    return IniciarMesResponse(
        periodo=periodo_validado,
        creadas=creadas,
        ya_existentes=ya_existentes,
    )


def emitir_cuenta_cobro(
    db: Session,
    cuenta_id: int,
    datos: EmitirCuentaSchema,
) -> CuentaCobro:
    """Redacta honorarios/valor, asigna consecutivo secuencial, emite y genera PDF."""
    cuenta_repo = CuentaCobroRepository(db)
    cuenta = cuenta_repo.get_with_cliente_or_404(cuenta_id)

    if cuenta.estado in {EstadoCuenta.PAGADA, EstadoCuenta.ANULADA}:
        raise BusinessRuleException(
            f"No se puede emitir una cuenta en estado {cuenta.estado.value}."
        )

    concepto_limpio = datos.concepto_honorarios.strip()
    if not concepto_limpio:
        raise BusinessRuleException("El concepto de honorarios no puede estar vacío.")
    if datos.valor_total <= Decimal("0.00"):
        raise BusinessRuleException("El valor total debe ser mayor a cero.")

    ruta_anterior = cuenta.ruta_pdf
    cambios: dict[str, object] = {
        "fecha_emision": datos.fecha_emision,
        "concepto_honorarios": concepto_limpio,
        "valor_total": datos.valor_total,
        "estado": EstadoCuenta.EMITIDA,
    }
    if cuenta.consecutivo is None:
        cambios["consecutivo"] = cuenta_repo.get_siguiente_consecutivo(
            datos.fecha_emision.year
        )
    if datos.observaciones_internas is not None:
        cambios["observaciones_internas"] = datos.observaciones_internas

    cuenta_repo.update(cuenta, cambios)
    cuenta_cargada = cuenta_repo.get_with_cliente_or_404(cuenta.id)
    emisor = obtener_emisor(db)
    ruta_pdf = pdf_service.generar_cuenta_pdf(
        cuenta_cargada, emisor, incluir_anexos=True
    )
    _limpiar_pdf_huerfano(ruta_anterior, ruta_pdf)
    cuenta_repo.update(cuenta_cargada, {"ruta_pdf": str(ruta_pdf)})
    return cuenta_repo.get_with_cliente_or_404(cuenta_cargada.id)


def crear_cobro_manual(db: Session, datos: CrearCobroManualSchema) -> CuentaCobro:
    """Crea una cuenta de cobro puntual en estado BORRADOR o EMITIDA."""
    cliente = ClienteRepository(db).get_or_404(datos.cliente_id, "Cliente")
    if not cliente.activo:
        raise BusinessRuleException(
            "No se puede crear una cuenta de cobro para un cliente inactivo."
        )
    if datos.estado not in {EstadoCuenta.BORRADOR, EstadoCuenta.EMITIDA}:
        raise BusinessRuleException(
            "Un cobro manual solo puede crearse en estado BORRADOR o EMITIDA."
        )

    cuenta_repo = CuentaCobroRepository(db)

    if datos.estado == EstadoCuenta.EMITIDA:
        concepto = (datos.concepto_honorarios or "").strip()
        if not concepto:
            raise BusinessRuleException(
                "El concepto de honorarios es obligatorio al crear una cuenta EMITIDA."
            )
        if datos.valor_total <= Decimal("0.00"):
            raise BusinessRuleException(
                "El valor total debe ser mayor a cero al crear una cuenta EMITIDA."
            )
        fecha_emision = datos.fecha_emision or date.today()
        consecutivo = cuenta_repo.get_siguiente_consecutivo(fecha_emision.year)
        cuenta = cuenta_repo.create(
            {
                "consecutivo": consecutivo,
                "cliente_id": cliente.id,
                "periodo_mes": datos.periodo_mes,
                "fecha_emision": fecha_emision,
                "concepto_honorarios": concepto,
                "valor_total": datos.valor_total,
                "estado": EstadoCuenta.EMITIDA,
                "observaciones_internas": datos.observaciones_internas,
            }
        )
        cuenta_cargada = cuenta_repo.get_with_cliente_or_404(cuenta.id)
        emisor = obtener_emisor(db)
        ruta_pdf = pdf_service.generar_cuenta_pdf(
            cuenta_cargada, emisor, incluir_anexos=True
        )
        cuenta_repo.update(cuenta_cargada, {"ruta_pdf": str(ruta_pdf)})
        return cuenta_repo.get_with_cliente_or_404(cuenta_cargada.id)

    cuenta = cuenta_repo.create(
        {
            "consecutivo": None,
            "cliente_id": cliente.id,
            "periodo_mes": datos.periodo_mes,
            "fecha_emision": datos.fecha_emision,
            "concepto_honorarios": (
                datos.concepto_honorarios.strip()
                if datos.concepto_honorarios
                else None
            ),
            "valor_total": datos.valor_total,
            "estado": EstadoCuenta.BORRADOR,
            "observaciones_internas": datos.observaciones_internas,
        }
    )
    return cuenta_repo.get_with_cliente_or_404(cuenta.id)


def regenerar_pdf(
    db: Session,
    cuenta_id: int,
    incluir_anexos: bool = True,
) -> Path:
    """Regenera el archivo PDF de una cuenta emitida o pagada y actualiza ruta_pdf."""
    cuenta_repo = CuentaCobroRepository(db)
    cuenta = cuenta_repo.get_with_cliente_or_404(cuenta_id)
    if cuenta.estado not in {EstadoCuenta.EMITIDA, EstadoCuenta.PAGADA}:
        raise BusinessRuleException(
            f"Solo se puede generar PDF para cuentas EMITIDA o PAGADA "
            f"(estado actual: {cuenta.estado.value})."
        )
    ruta_anterior = cuenta.ruta_pdf
    emisor = obtener_emisor(db)
    ruta_pdf = pdf_service.generar_cuenta_pdf(
        cuenta, emisor, incluir_anexos=incluir_anexos
    )
    _limpiar_pdf_huerfano(ruta_anterior, ruta_pdf)
    cuenta_repo.update(cuenta, {"ruta_pdf": str(ruta_pdf)})
    return ruta_pdf


def obtener_o_generar_pdf(
    db: Session,
    cuenta_id: int,
    incluir_anexos: bool = True,
    regenerar: bool = False,
) -> Path:
    """Retorna la ruta del PDF existente o lo genera al vuelo si falta o se solicita regenerar."""
    cuenta = CuentaCobroRepository(db).get_with_cliente_or_404(cuenta_id)
    if regenerar or not cuenta.ruta_pdf or not Path(cuenta.ruta_pdf).is_file():
        return regenerar_pdf(db, cuenta_id, incluir_anexos=incluir_anexos)
    return Path(cuenta.ruta_pdf)


def abrir_carpeta_periodo(periodo_mes: str) -> Path:
    """Crea si no existe y abre en el explorador del sistema la carpeta del periodo YYYY-MM."""
    periodo_validado = _validar_periodo_o_400(periodo_mes)
    carpeta = pdf_service.obtener_carpeta_periodo(periodo_validado)
    sistema = platform.system()
    if sistema == "Windows":
        os.startfile(str(carpeta))  # type: ignore[attr-defined]
    elif sistema == "Darwin":
        subprocess.Popen(["open", str(carpeta)])
    else:
        subprocess.Popen(["xdg-open", str(carpeta)])
    return carpeta


def cambiar_estado_pago(
    db: Session,
    cuenta_id: int,
    pagada: bool,
    fecha_pago: Optional[date] = None,
) -> CuentaCobro:
    """Marca una cuenta EMITIDA como PAGADA o revierte una PAGADA a EMITIDA."""
    cuenta_repo = CuentaCobroRepository(db)
    cuenta = cuenta_repo.get_with_cliente_or_404(cuenta_id)

    if pagada:
        if cuenta.estado != EstadoCuenta.EMITIDA:
            raise BusinessRuleException(
                f"Solo se pueden marcar como pagadas cuentas en estado EMITIDA "
                f"(estado actual: {cuenta.estado.value})."
            )
        cuenta_repo.update(
            cuenta,
            {
                "estado": EstadoCuenta.PAGADA,
                "fecha_pago": fecha_pago or date.today(),
            },
        )
    else:
        if cuenta.estado != EstadoCuenta.PAGADA:
            raise BusinessRuleException(
                f"Solo se puede revertir el pago de cuentas en estado PAGADA "
                f"(estado actual: {cuenta.estado.value})."
            )
        cuenta_repo.update(
            cuenta,
            {
                "estado": EstadoCuenta.EMITIDA,
                "fecha_pago": None,
            },
        )

    return cuenta_repo.get_with_cliente_or_404(cuenta.id)


def anular_cuenta_cobro(
    db: Session,
    cuenta_id: int,
    observaciones_internas: Optional[str] = None,
) -> CuentaCobro:
    """Anula una cuenta conservando su consecutivo para trazabilidad de auditoría."""
    cuenta_repo = CuentaCobroRepository(db)
    cuenta = cuenta_repo.get_with_cliente_or_404(cuenta_id)

    if cuenta.estado == EstadoCuenta.ANULADA:
        raise BusinessRuleException("La cuenta de cobro ya se encuentra anulada.")
    if cuenta.estado == EstadoCuenta.PAGADA:
        raise BusinessRuleException(
            "No se puede anular una cuenta PAGADA. Revierta el pago primero."
        )

    cambios: dict[str, object] = {"estado": EstadoCuenta.ANULADA}
    if observaciones_internas is not None:
        cambios["observaciones_internas"] = observaciones_internas

    cuenta_repo.update(cuenta, cambios)
    return cuenta_repo.get_with_cliente_or_404(cuenta.id)


def eliminar_cuenta_borrador(db: Session, cuenta_id: int) -> None:
    """Elimina físicamente una cuenta únicamente si está en estado BORRADOR."""
    cuenta_repo = CuentaCobroRepository(db)
    cuenta = cuenta_repo.get_with_cliente_or_404(cuenta_id)
    if cuenta.estado != EstadoCuenta.BORRADOR:
        raise BusinessRuleException(
            f"Solo se pueden eliminar cuentas en estado BORRADOR "
            f"(estado actual: {cuenta.estado.value}). Use anulación para cuentas emitidas."
        )
    cuenta_repo.delete(cuenta)


def obtener_tablero_mensual(
    db: Session,
    periodo_mes: str,
) -> TableroMensualResponse:
    """Retorna el To-Do List del mes, la cartera vencida de meses previos y los KPIs."""
    periodo_validado = _validar_periodo_o_400(periodo_mes)
    cuenta_repo = CuentaCobroRepository(db)

    cuentas_mes = cuenta_repo.listar_por_periodo(periodo_validado)
    cuentas_mes.sort(
        key=lambda c: (_ORDEN_ESTADO_TABLERO.get(c.estado, 99), c.id)
    )

    cartera_vencida = cuenta_repo.listar_cartera_vencida(periodo_validado)

    total_recaudado_mes = sum(
        (c.valor_total for c in cuentas_mes if c.estado == EstadoCuenta.PAGADA),
        Decimal("0.00"),
    )
    total_por_cobrar_mes = sum(
        (c.valor_total for c in cuentas_mes if c.estado == EstadoCuenta.EMITIDA),
        Decimal("0.00"),
    )
    total_facturado_mes = total_recaudado_mes + total_por_cobrar_mes
    total_cartera_vencida_historica = sum(
        (c.valor_total for c in cartera_vencida),
        Decimal("0.00"),
    )
    pendientes_por_redactar = sum(
        1 for c in cuentas_mes if c.estado == EstadoCuenta.BORRADOR
    )

    kpis = TableroKPIsResponse(
        total_facturado_mes=total_facturado_mes,
        total_recaudado_mes=total_recaudado_mes,
        total_por_cobrar_mes=total_por_cobrar_mes,
        total_cartera_vencida_historica=total_cartera_vencida_historica,
        pendientes_por_redactar=pendientes_por_redactar,
    )

    return TableroMensualResponse(
        periodo_mes=periodo_validado,
        cuentas_del_mes=cuentas_mes,
        cartera_vencida=cartera_vencida,
        kpis=kpis,
    )
