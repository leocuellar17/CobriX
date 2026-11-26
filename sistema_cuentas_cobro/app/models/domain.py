"""Modelos ORM SQLAlchemy 2.0 y enumeraciones del dominio de Cuentas de Cobro."""

from datetime import date, datetime, timezone
from decimal import Decimal
import enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    """Retorna la fecha y hora actual en UTC."""
    return datetime.now(timezone.utc)


class TipoPersona(str, enum.Enum):
    """Clasificación tributaria del cliente en Colombia."""

    NATURAL = "NATURAL"
    JURIDICA = "JURIDICA"


class EstadoCuenta(str, enum.Enum):
    """Ciclo de vida de una Cuenta de Cobro."""

    BORRADOR = "BORRADOR"
    EMITIDA = "EMITIDA"
    PAGADA = "PAGADA"
    ANULADA = "ANULADA"


DEFAULT_NOTA_LEGAL_IVA = (
    "No responsable de IVA según Art. 437 Parágrafo 3 del Estatuto Tributario. "
    "Actividad económica de servicios profesionales independientes."
)

DEFAULT_NOTA_RETENCION = (
    "Solicito aplicación de la tabla de retención en la fuente del Art. 383 del "
    "Estatuto Tributario, manifestando bajo gravedad de juramento que no he "
    "contratado ni vinculado dos (2) o más trabajadores asociados a la actividad."
)


class Emisor(Base):
    """Perfil único (id=1) del profesional independiente emisor de cuentas."""

    __tablename__ = "emisor"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(
        String(20), nullable=False, default="C.C."
    )
    numero_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    rut: Mapped[str] = mapped_column(String(50), nullable=False)
    direccion: Mapped[str] = mapped_column(String(255), nullable=False)
    ciudad: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Bogotá D.C."
    )
    telefono: Mapped[str] = mapped_column(String(50), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), nullable=False)
    banco: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_cuenta: Mapped[str] = mapped_column(String(50), nullable=False)
    numero_cuenta: Mapped[str] = mapped_column(String(50), nullable=False)
    nota_legal_iva: Mapped[str] = mapped_column(
        Text, nullable=False, default=DEFAULT_NOTA_LEGAL_IVA
    )
    nota_retencion: Mapped[str] = mapped_column(
        Text, nullable=False, default=DEFAULT_NOTA_RETENCION
    )
    ruta_firma: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ruta_rut_pdf: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ruta_cert_bancaria_pdf: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class Cliente(Base):
    """Cliente (empresa o persona natural) a quien se le emiten cuentas de cobro."""

    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tipo_persona: Mapped[TipoPersona] = mapped_column(
        SAEnum(TipoPersona, native_enum=False),
        nullable=False,
    )
    nombre_razon_social: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    documento_nit: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    direccion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ciudad: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Bogotá D.C."
    )
    correo_contacto: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    es_recurrente: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    cuentas: Mapped[list["CuentaCobro"]] = relationship(back_populates="cliente")


class CuentaCobro(Base):
    """Documento de cuenta de cobro mensual o extraordinario asociado a un cliente."""

    __tablename__ = "cuentas_cobro"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    consecutivo: Mapped[Optional[str]] = mapped_column(
        String(30), unique=True, index=True, nullable=True
    )
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id"), nullable=False
    )
    periodo_mes: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    fecha_emision: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    concepto_honorarios: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    valor_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    estado: Mapped[EstadoCuenta] = mapped_column(
        SAEnum(EstadoCuenta, native_enum=False),
        nullable=False,
        default=EstadoCuenta.BORRADOR,
        index=True,
    )
    fecha_pago: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    observaciones_internas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ruta_pdf: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    cliente: Mapped["Cliente"] = relationship(back_populates="cuentas")
