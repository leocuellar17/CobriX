"""Esquemas Pydantic v2 para validación de peticiones y serialización de respuestas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.utils import validar_periodo_mes
from app.models.domain import EstadoCuenta, TipoPersona


# ---------------------------------------------------------------------------
# Emisor
# ---------------------------------------------------------------------------


class EmisorUpdate(BaseModel):
    """Datos para actualizar el perfil único del emisor."""

    nombre_completo: str = Field(..., min_length=2, max_length=200)
    tipo_documento: str = Field(default="C.C.", min_length=2, max_length=20)
    numero_documento: str = Field(..., min_length=3, max_length=50)
    rut: str = Field(..., min_length=3, max_length=50)
    direccion: str = Field(..., min_length=3, max_length=255)
    ciudad: str = Field(default="Bogotá D.C.", min_length=2, max_length=100)
    telefono: str = Field(..., min_length=5, max_length=50)
    correo: str = Field(..., min_length=5, max_length=150)
    banco: str = Field(..., min_length=2, max_length=100)
    tipo_cuenta: str = Field(..., min_length=3, max_length=50)
    numero_cuenta: str = Field(..., min_length=4, max_length=50)
    nota_legal_iva: str = Field(..., min_length=10)
    nota_retencion: str = Field(..., min_length=10)
    ruta_firma: Optional[str] = Field(default=None, max_length=500)
    ruta_rut_pdf: Optional[str] = Field(default=None, max_length=500)
    ruta_cert_bancaria_pdf: Optional[str] = Field(default=None, max_length=500)


class EmisorResponse(BaseModel):
    """Respuesta estructurada del perfil del emisor."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_completo: str
    tipo_documento: str
    numero_documento: str
    rut: str
    direccion: str
    ciudad: str
    telefono: str
    correo: str
    banco: str
    tipo_cuenta: str
    numero_cuenta: str
    nota_legal_iva: str
    nota_retencion: str
    ruta_firma: Optional[str] = None
    ruta_rut_pdf: Optional[str] = None
    ruta_cert_bancaria_pdf: Optional[str] = None
    updated_at: datetime


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


class ClienteBase(BaseModel):
    """Campos compartidos para creación y lectura de clientes."""

    tipo_persona: TipoPersona
    nombre_razon_social: str = Field(..., min_length=2, max_length=255)
    documento_nit: str = Field(..., min_length=3, max_length=50)
    direccion: Optional[str] = Field(default=None, max_length=255)
    ciudad: str = Field(default="Bogotá D.C.", min_length=2, max_length=100)
    correo_contacto: Optional[str] = Field(default=None, max_length=150)
    telefono: Optional[str] = Field(default=None, max_length=50)
    es_recurrente: bool = True

    @field_validator("nombre_razon_social", "documento_nit")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """Elimina espacios extremos y rechaza cadenas vacías."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El campo no puede estar vacío.")
        return cleaned


class ClienteCreate(ClienteBase):
    """Esquema para registrar un nuevo cliente."""


class ClienteUpdate(BaseModel):
    """Esquema para actualizar un cliente existente."""

    tipo_persona: Optional[TipoPersona] = None
    nombre_razon_social: Optional[str] = Field(default=None, min_length=2, max_length=255)
    documento_nit: Optional[str] = Field(default=None, min_length=3, max_length=50)
    direccion: Optional[str] = Field(default=None, max_length=255)
    ciudad: Optional[str] = Field(default=None, min_length=2, max_length=100)
    correo_contacto: Optional[str] = Field(default=None, max_length=150)
    telefono: Optional[str] = Field(default=None, max_length=50)
    es_recurrente: Optional[bool] = None

    @field_validator("nombre_razon_social", "documento_nit")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        """Normaliza texto si se envía en la actualización."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El campo no puede estar vacío.")
        return cleaned


class ClienteEstadoUpdate(BaseModel):
    """Esquema para activar o desactivar (soft delete) un cliente."""

    activo: bool


class ClienteResumenResponse(BaseModel):
    """Información resumida del cliente embebida en cuentas de cobro."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_persona: TipoPersona
    nombre_razon_social: str
    documento_nit: str


class ClienteResponse(BaseModel):
    """Respuesta completa de un cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_persona: TipoPersona
    nombre_razon_social: str
    documento_nit: str
    direccion: Optional[str] = None
    ciudad: str
    correo_contacto: Optional[str] = None
    telefono: Optional[str] = None
    es_recurrente: bool
    activo: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Cuentas de Cobro y Tablero
# ---------------------------------------------------------------------------


class IniciarMesRequest(BaseModel):
    """Solicitud para generar tareas mensuales de cobro para clientes recurrentes."""

    periodo_mes: str = Field(..., examples=["2026-12"])

    @field_validator("periodo_mes")
    @classmethod
    def check_periodo(cls, value: str) -> str:
        return validar_periodo_mes(value)


class IniciarMesResponse(BaseModel):
    """Resumen idempotente de apertura de mes."""

    periodo: str
    creadas: int
    ya_existentes: int


class EmitirCuentaSchema(BaseModel):
    """Datos requeridos para redactar y emitir una cuenta de cobro."""

    fecha_emision: date
    concepto_honorarios: str = Field(..., min_length=3)
    valor_total: Decimal = Field(..., gt=Decimal("0.00"), max_digits=14, decimal_places=2)
    observaciones_internas: Optional[str] = None

    @field_validator("concepto_honorarios")
    @classmethod
    def check_concepto_no_vacio(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El concepto de honorarios no puede estar vacío.")
        return cleaned


class CrearCobroManualSchema(BaseModel):
    """Esquema para crear una cuenta de cobro puntual (extraordinaria)."""

    cliente_id: int = Field(..., gt=0)
    periodo_mes: str = Field(..., examples=["2026-12"])
    estado: EstadoCuenta = EstadoCuenta.EMITIDA
    fecha_emision: Optional[date] = None
    concepto_honorarios: Optional[str] = None
    valor_total: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    observaciones_internas: Optional[str] = None

    @field_validator("periodo_mes")
    @classmethod
    def check_periodo(cls, value: str) -> str:
        return validar_periodo_mes(value)


class PagoCuentaRequest(BaseModel):
    """Solicitud para marcar o desmarcar una cuenta como pagada."""

    pagada: bool
    fecha_pago: Optional[date] = None


class AnularCuentaRequest(BaseModel):
    """Solicitud opcional con motivo al anular una cuenta de cobro."""

    observaciones_internas: Optional[str] = None


class CuentaCobroResponse(BaseModel):
    """Respuesta completa de una Cuenta de Cobro."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    consecutivo: Optional[str] = None
    cliente_id: int
    periodo_mes: str
    fecha_emision: Optional[date] = None
    concepto_honorarios: Optional[str] = None
    valor_total: Decimal
    estado: EstadoCuenta
    fecha_pago: Optional[date] = None
    observaciones_internas: Optional[str] = None
    ruta_pdf: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    cliente: ClienteResumenResponse


class TableroKPIsResponse(BaseModel):
    """Indicadores financieros del periodo y cartera vencida histórica."""

    total_facturado_mes: Decimal
    total_recaudado_mes: Decimal
    total_por_cobrar_mes: Decimal
    total_cartera_vencida_historica: Decimal
    pendientes_por_redactar: int


class TableroMensualResponse(BaseModel):
    """Vista consolidada de To-Do List mensual, cartera vencida y KPIs."""

    periodo_mes: str
    cuentas_del_mes: list[CuentaCobroResponse]
    cartera_vencida: list[CuentaCobroResponse]
    kpis: TableroKPIsResponse
