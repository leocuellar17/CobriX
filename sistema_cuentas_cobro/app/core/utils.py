"""Utilidades y constantes centralizadas de formato, validación y rutas en español."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re

from num2words import num2words

from app.core.exceptions import BusinessRuleException


PERIODO_MES_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

MESES_CARPETA: dict[int, str] = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|.]+')
_WHITESPACE_PATTERN = re.compile(r"\s+")


def validar_periodo_mes(valor: str) -> str:
    """Valida que el periodo mensual tenga formato estricto YYYY-MM."""
    limpio = valor.strip()
    if not PERIODO_MES_PATTERN.match(limpio):
        raise ValueError(
            "El periodo debe tener formato YYYY-MM válido (ej. '2026-12')."
        )
    return limpio


def monto_a_letras_cop(valor: Decimal) -> str:
    """Convierte un valor Decimal en pesos colombianos a su representación formal en letras."""
    entero = int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    if entero < 0:
        raise BusinessRuleException("El valor monetario no puede ser negativo.")
    if entero == 0:
        return "CERO PESOS M/CTE"
    if entero == 1:
        return "UN PESO M/CTE"

    texto = num2words(entero, lang="es").upper()
    texto = re.sub(r"\bVEINTIUNO$", "VEINTIÚN", texto)
    texto = re.sub(r"\bUNO$", "UN", texto)
    texto = re.sub(r"\bUNO(?=\s+MILL[ÓO]N)", "UN", texto)

    if entero >= 1_000_000 and entero % 1_000_000 == 0:
        return f"{texto} DE PESOS M/CTE"
    return f"{texto} PESOS M/CTE"


def formatear_moneda_cop(valor: Decimal) -> str:
    """Formatea un valor Decimal en pesos colombianos con separador de miles por punto."""
    entero = int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"${entero:,}".replace(",", ".")


def formatear_fecha_es(fecha: date) -> str:
    """Formatea una fecha como '15 de diciembre de 2026'."""
    nombre_mes = MESES_CARPETA[fecha.month].lower()
    return f"{fecha.day} de {nombre_mes} de {fecha.year}"


def sanitizar_nombre_archivo(nombre: str) -> str:
    """Elimina caracteres inválidos de Windows/Unix y normaliza espacios para nombres de archivo."""
    limpio = _INVALID_FILENAME_CHARS.sub("", nombre.strip())
    limpio = _WHITESPACE_PATTERN.sub("_", limpio)
    limpio = re.sub(r"_+", "_", limpio).strip("_")
    return limpio or "Cliente"


def resolver_carpeta_periodo(
    base_dir: Path,
    periodo_mes: str,
    crear: bool = True,
) -> Path:
    """Retorna la ruta {base_dir}/{YYYY}/{MM}_{NombreMes} validando el periodo."""
    periodo_validado = validar_periodo_mes(periodo_mes)
    anio_str, mes_str = periodo_validado.split("-")
    mes = int(mes_str)
    carpeta = base_dir / anio_str / f"{mes:02d}_{MESES_CARPETA[mes]}"
    if crear:
        carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta
