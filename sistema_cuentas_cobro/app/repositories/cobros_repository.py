"""Repositorios especializados para Emisor, Cliente y CuentaCobro."""

import re
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import EntityNotFoundException
from app.models.domain import (
    Cliente,
    CuentaCobro,
    DEFAULT_NOTA_LEGAL_IVA,
    DEFAULT_NOTA_RETENCION,
    Emisor,
    EstadoCuenta,
)
from app.repositories.base import BaseRepository


_CONSECUTIVO_NUM_REGEX = re.compile(r"^CC-\d{4}-(\d+)$")


class EmisorRepository(BaseRepository[Emisor]):
    """Repositorio para el perfil único del emisor (id=1)."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Emisor)

    def get_or_create_default(self) -> Emisor:
        """Retorna el emisor id=1 o lo crea con valores plantilla iniciales."""
        emisor = self.get_by_id(1)
        if emisor is not None:
            return emisor

        return self.create(
            {
                "id": 1,
                "nombre_completo": "Profesional Independiente (Editar Perfil)",
                "tipo_documento": "C.C.",
                "numero_documento": "0000000000",
                "rut": "0000000000-0",
                "direccion": "Dirección por configurar",
                "ciudad": "Bogotá D.C.",
                "telefono": "3000000000",
                "correo": "correo@ejemplo.com",
                "banco": "Banco por configurar",
                "tipo_cuenta": "Ahorros",
                "numero_cuenta": "00000000000",
                "nota_legal_iva": DEFAULT_NOTA_LEGAL_IVA,
                "nota_retencion": DEFAULT_NOTA_RETENCION,
            }
        )


class ClienteRepository(BaseRepository[Cliente]):
    """Repositorio especializado para consultas de clientes."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Cliente)

    def get_by_documento(
        self,
        documento_nit: str,
        exclude_id: Optional[int] = None,
    ) -> Optional[Cliente]:
        """Busca un cliente por número de documento/NIT, excluyendo opcionalmente un ID."""
        stmt = select(Cliente).where(Cliente.documento_nit == documento_nit)
        if exclude_id is not None:
            stmt = stmt.where(Cliente.id != exclude_id)
        return self.db.scalar(stmt)

    def listar_filtrados(
        self,
        solo_activos: bool = True,
        busqueda: Optional[str] = None,
    ) -> list[Cliente]:
        """Lista clientes ordenados alfabéticamente con filtro de estado y búsqueda."""
        stmt = select(Cliente)
        if solo_activos:
            stmt = stmt.where(Cliente.activo.is_(True))
        if busqueda and busqueda.strip():
            termino = f"%{busqueda.strip()}%"
            stmt = stmt.where(
                or_(
                    Cliente.nombre_razon_social.ilike(termino),
                    Cliente.documento_nit.ilike(termino),
                )
            )
        stmt = stmt.order_by(Cliente.nombre_razon_social.asc())
        return list(self.db.scalars(stmt).all())

    def listar_recurrentes_activos(self) -> list[Cliente]:
        """Retorna los clientes activos marcados como recurrentes mensuales."""
        stmt = select(Cliente).where(
            Cliente.activo.is_(True),
            Cliente.es_recurrente.is_(True),
        )
        return list(self.db.scalars(stmt).all())


class CuentaCobroRepository(BaseRepository[CuentaCobro]):
    """Repositorio especializado para cuentas de cobro, consecutivos y cartera."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, CuentaCobro)

    def get_with_cliente_or_404(self, cuenta_id: int) -> CuentaCobro:
        """Obtiene una cuenta con su relación `cliente` cargada o lanza 404."""
        stmt = (
            select(CuentaCobro)
            .options(joinedload(CuentaCobro.cliente))
            .where(CuentaCobro.id == cuenta_id)
        )
        cuenta = self.db.scalar(stmt)
        if cuenta is None:
            raise EntityNotFoundException("Cuenta de cobro", cuenta_id)
        return cuenta

    def get_clientes_con_cuenta_en_periodo(self, periodo_mes: str) -> set[int]:
        """Retorna IDs de clientes que ya tienen cuenta no anulada en el periodo."""
        stmt = select(CuentaCobro.cliente_id).where(
            CuentaCobro.periodo_mes == periodo_mes,
            CuentaCobro.estado != EstadoCuenta.ANULADA,
        )
        return set(self.db.scalars(stmt).all())

    def get_siguiente_consecutivo(self, anio: int) -> str:
        """Calcula el siguiente consecutivo secuencial CC-{AÑO}-{NUMERO_4_DIGITOS}."""
        prefijo = f"CC-{anio}-"
        consecutivos = self.db.scalars(
            select(CuentaCobro.consecutivo).where(
                CuentaCobro.consecutivo.like(f"{prefijo}%")
            )
        ).all()

        max_numero = 0
        for item in consecutivos:
            if item is None:
                continue
            match = _CONSECUTIVO_NUM_REGEX.match(item)
            if match:
                numero = int(match.group(1))
                if numero > max_numero:
                    max_numero = numero

        return f"{prefijo}{max_numero + 1:04d}"

    def listar_por_periodo(self, periodo_mes: str) -> list[CuentaCobro]:
        """Retorna todas las cuentas del periodo con el cliente precargado."""
        stmt = (
            select(CuentaCobro)
            .options(joinedload(CuentaCobro.cliente))
            .where(CuentaCobro.periodo_mes == periodo_mes)
        )
        return list(self.db.scalars(stmt).all())

    def listar_cartera_vencida(self, periodo_mes: str) -> list[CuentaCobro]:
        """Retorna cuentas EMITIDA de periodos estrictamente anteriores al consultado."""
        stmt = (
            select(CuentaCobro)
            .options(joinedload(CuentaCobro.cliente))
            .where(
                CuentaCobro.estado == EstadoCuenta.EMITIDA,
                CuentaCobro.periodo_mes < periodo_mes,
            )
            .order_by(CuentaCobro.periodo_mes.asc(), CuentaCobro.id.asc())
        )
        return list(self.db.scalars(stmt).all())
