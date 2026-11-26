"""Servicio de generación documental PDF, incrustación de firma y fusión de anexos."""

import base64
import io
import logging
from pathlib import Path
from typing import Literal, Optional

from fastapi import UploadFile
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter
from xhtml2pdf import pisa

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.core.utils import (
    MESES_CARPETA,
    formatear_fecha_es,
    formatear_moneda_cop,
    monto_a_letras_cop,
    resolver_carpeta_periodo,
    sanitizar_nombre_archivo,
)
from app.models.domain import CuentaCobro, Emisor


logger = logging.getLogger(__name__)

EXTENSIONES_PERMITIDAS: dict[str, set[str]] = {
    "firma": {".png", ".jpg", ".jpeg"},
    "rut": {".pdf"},
    "cert_bancaria": {".pdf"},
}


class PDFService:
    """Motor de renderizado HTML->PDF, incrustación de firma y fusión de anexos."""

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        assets_dir: Optional[Path] = None,
    ) -> None:
        self.templates_dir: Path = templates_dir or settings.TEMPLATES_DIR
        self.output_dir: Path = output_dir or settings.OUTPUT_PDF_DIR
        self.assets_dir: Path = assets_dir or settings.ASSETS_DIR
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def obtener_carpeta_periodo(self, periodo_mes: str) -> Path:
        """Retorna y crea la carpeta de salida para un periodo YYYY-MM."""
        return resolver_carpeta_periodo(self.output_dir, periodo_mes, crear=True)

    def _cargar_firma_base64(
        self, ruta_firma: Optional[str]
    ) -> tuple[Optional[str], str]:
        """Codifica la imagen de firma en Base64 para evitar errores de ruta en xhtml2pdf."""
        if not ruta_firma:
            return None, "image/png"

        path_firma = Path(ruta_firma)
        if not path_firma.is_file():
            logger.warning(
                "Archivo de firma no encontrado en '%s'. Se generará el PDF sin firma.",
                path_firma,
            )
            return None, "image/png"

        ext = path_firma.suffix.lower()
        mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
        contenido_b64 = base64.b64encode(path_firma.read_bytes()).decode("ascii")
        return contenido_b64, mime

    def _adjuntar_anexo_pdf(
        self, writer: PdfWriter, ruta_anexo: Optional[str], etiqueta: str
    ) -> None:
        """Adjunta las páginas de un anexo PDF al escritor si el archivo existe en disco."""
        if not ruta_anexo:
            return

        path_anexo = Path(ruta_anexo)
        if not path_anexo.is_file():
            logger.warning(
                "Anexo '%s' configurado en '%s' no existe en disco. Se omite sin error.",
                etiqueta,
                path_anexo,
            )
            return

        try:
            reader = PdfReader(str(path_anexo))
            for page in reader.pages:
                writer.add_page(page)
        except Exception as exc:
            logger.warning(
                "No se pudo leer el anexo '%s' en '%s': %s. Se omite sin error.",
                etiqueta,
                path_anexo,
                exc,
            )

    def generar_cuenta_pdf(
        self,
        cuenta: CuentaCobro,
        emisor: Emisor,
        incluir_anexos: bool = True,
    ) -> Path:
        """Renderiza la cuenta de cobro a PDF, fusiona anexos opcionales y guarda en disco."""
        if cuenta.fecha_emision is None or not cuenta.consecutivo:
            raise BusinessRuleException(
                "La cuenta debe estar emitida con fecha y consecutivo para generar el PDF."
            )
        if not cuenta.concepto_honorarios:
            raise BusinessRuleException(
                "La cuenta debe tener concepto de honorarios para generar el PDF."
            )

        fecha = cuenta.fecha_emision
        carpeta_destino = (
            self.output_dir
            / f"{fecha.year}"
            / f"{fecha.month:02d}_{MESES_CARPETA[fecha.month]}"
        )
        carpeta_destino.mkdir(parents=True, exist_ok=True)

        cliente_sanitizado = sanitizar_nombre_archivo(cuenta.cliente.nombre_razon_social)
        nombre_archivo = f"{cuenta.consecutivo}_{cliente_sanitizado}.pdf"
        ruta_final = carpeta_destino / nombre_archivo

        firma_base64, firma_mime = self._cargar_firma_base64(emisor.ruta_firma)
        template = self._jinja_env.get_template("cuenta_cobro.html")
        html_renderizado = template.render(
            cuenta=cuenta,
            emisor=emisor,
            cliente=cuenta.cliente,
            fecha_formateada=formatear_fecha_es(fecha),
            valor_letras=monto_a_letras_cop(cuenta.valor_total),
            valor_formateado=formatear_moneda_cop(cuenta.valor_total),
            firma_base64=firma_base64,
            firma_mime=firma_mime,
        )

        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(
            io.BytesIO(html_renderizado.encode("utf-8")),
            dest=pdf_buffer,
            encoding="utf-8",
        )
        if pisa_status.err:
            raise BusinessRuleException(
                "Ocurrió un error interno al renderizar el PDF de la cuenta de cobro."
            )

        pdf_buffer.seek(0)

        if incluir_anexos:
            writer = PdfWriter()
            principal_reader = PdfReader(pdf_buffer)
            for page in principal_reader.pages:
                writer.add_page(page)

            self._adjuntar_anexo_pdf(writer, emisor.ruta_rut_pdf, "RUT")
            self._adjuntar_anexo_pdf(
                writer, emisor.ruta_cert_bancaria_pdf, "Certificación Bancaria"
            )

            with ruta_final.open("wb") as salida:
                writer.write(salida)
        else:
            ruta_final.write_bytes(pdf_buffer.getvalue())

        return ruta_final

    def guardar_archivo_emisor(
        self,
        tipo_archivo: Literal["firma", "rut", "cert_bancaria"],
        file: UploadFile,
    ) -> str:
        """Valida extensión y guarda de forma segura firma o anexos PDF en archivos/assets/."""
        if tipo_archivo not in EXTENSIONES_PERMITIDAS:
            raise BusinessRuleException(f"Tipo de archivo no soportado: '{tipo_archivo}'.")

        nombre_original = Path(file.filename or "").name
        extension = Path(nombre_original).suffix.lower()
        permitidas = EXTENSIONES_PERMITIDAS[tipo_archivo]

        if extension not in permitidas:
            raise BusinessRuleException(
                f"Extensión '{extension or 'sin extensión'}' inválida para '{tipo_archivo}'. "
                f"Permitidas: {', '.join(sorted(permitidas))}."
            )

        self.assets_dir.mkdir(parents=True, exist_ok=True)
        destino = self.assets_dir / f"{tipo_archivo}{extension}"
        contenido = file.file.read()
        if not contenido:
            raise BusinessRuleException("El archivo subido está vacío.")

        destino.write_bytes(contenido)
        return str(destino)


pdf_service = PDFService()
