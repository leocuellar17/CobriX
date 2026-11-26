"""Suite unificada de pruebas E2E para el Sistema de Cuentas de Cobro (CobriX)."""

from decimal import Decimal
import io
import logging
import os
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
import pytest

from app.core.exceptions import BusinessRuleException
from app.core.utils import monto_a_letras_cop, sanitizar_nombre_archivo
from app.services import backup_service


def _crear_pdf_dummy_bytes(num_paginas: int = 1) -> bytes:
    """Genera un PDF válido en memoria con el número de páginas indicado."""
    writer = PdfWriter()
    for _ in range(num_paginas):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _crear_png_1x1_bytes() -> bytes:
    """Genera una imagen PNG válida de 1x1 píxel."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00"
        b"\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )


# ---------------------------------------------------------------------------
# 1. Gestión del Emisor y Archivos
# ---------------------------------------------------------------------------


def test_e2e_gestion_emisor_y_archivos(client: TestClient) -> None:
    """Valida lectura, actualización del emisor y carga de firma y anexos PDF."""
    resp_get = client.get("/api/v1/emisor")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == 1

    payload_emisor = {
        "nombre_completo": "Leonardo Cuéllar",
        "tipo_documento": "C.C.",
        "numero_documento": "1018456789",
        "rut": "1018456789-3",
        "direccion": "Calle 85 # 15-20",
        "ciudad": "Bogotá D.C.",
        "telefono": "3105551234",
        "correo": "leonardo@cobrix.co",
        "banco": "Bancolombia",
        "tipo_cuenta": "Ahorros",
        "numero_cuenta": "12345678901",
        "nota_legal_iva": "No responsable de IVA según Art. 437 Parágrafo 3 E.T.",
        "nota_retencion": "Solicito aplicación tabla Art. 383 E.T. sin subcontratación.",
    }
    resp_put = client.put("/api/v1/emisor", json=payload_emisor)
    assert resp_put.status_code == 200
    assert resp_put.json()["nombre_completo"] == "Leonardo Cuéllar"

    # Subida de firma PNG y anexos PDF
    resp_firma = client.post(
        "/api/v1/emisor/archivos/firma",
        files={"file": ("mi_firma.png", _crear_png_1x1_bytes(), "image/png")},
    )
    assert resp_firma.status_code == 200
    assert Path(resp_firma.json()["ruta_firma"]).is_file()

    resp_rut = client.post(
        "/api/v1/emisor/archivos/rut",
        files={"file": ("rut.pdf", _crear_pdf_dummy_bytes(1), "application/pdf")},
    )
    assert resp_rut.status_code == 200
    assert Path(resp_rut.json()["ruta_rut_pdf"]).is_file()

    resp_cert = client.post(
        "/api/v1/emisor/archivos/cert_bancaria",
        files={"file": ("cert.pdf", _crear_pdf_dummy_bytes(2), "application/pdf")},
    )
    assert resp_cert.status_code == 200
    assert Path(resp_cert.json()["ruta_cert_bancaria_pdf"]).is_file()

    # Extensión inválida debe rechazarse con 400
    resp_invalido = client.post(
        "/api/v1/emisor/archivos/rut",
        files={"file": ("rut.exe", b"malware", "application/octet-stream")},
    )
    assert resp_invalido.status_code == 400


# ---------------------------------------------------------------------------
# 2. CRUD de Clientes
# ---------------------------------------------------------------------------


def test_e2e_crud_clientes_y_filtros(client: TestClient) -> None:
    """Valida creación Natural/Jurídica, unicidad NIT, edición, soft delete y búsqueda."""
    c_nat = client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "NATURAL",
            "nombre_razon_social": "Laura Gómez",
            "documento_nit": "52987654",
            "es_recurrente": True,
        },
    )
    assert c_nat.status_code == 201

    c_jur = client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "JURIDICA",
            "nombre_razon_social": "Andes Tech S.A.S.",
            "documento_nit": "900123456-7",
            "direccion": "Cra 7 # 71-21",
            "es_recurrente": True,
        },
    )
    assert c_jur.status_code == 201
    jur_id = c_jur.json()["id"]

    # Documento duplicado -> 409 Conflict
    dup = client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "JURIDICA",
            "nombre_razon_social": "Duplicada S.A.S.",
            "documento_nit": "900123456-7",
        },
    )
    assert dup.status_code == 409

    # Edición y búsqueda
    upd = client.put(
        f"/api/v1/clientes/{jur_id}",
        json={"correo_contacto": "facturacion@andestech.co"},
    )
    assert upd.status_code == 200
    assert upd.json()["correo_contacto"] == "facturacion@andestech.co"

    busqueda = client.get("/api/v1/clientes?busqueda=Andes")
    assert busqueda.status_code == 200
    assert len(busqueda.json()) == 1

    # Soft delete y filtro solo_activos
    off = client.patch(f"/api/v1/clientes/{jur_id}/estado", json={"activo": False})
    assert off.status_code == 200
    assert off.json()["activo"] is False

    activos = client.get("/api/v1/clientes?solo_activos=true")
    assert len(activos.json()) == 1
    todos = client.get("/api/v1/clientes?solo_activos=false")
    assert len(todos.json()) == 2


# ---------------------------------------------------------------------------
# 3. Flujo Mensual Autónomo (To-Do List) y Casos Borde
# ---------------------------------------------------------------------------


def test_e2e_flujo_mensual_todo_list_completo(client: TestClient) -> None:
    """Valida ciclo completo: apertura idempotente, emisión, edición, pago, reversión y bloqueos."""
    # Iniciar mes sin clientes recurrentes no falla
    vacio = client.post("/api/v1/cuentas/iniciar-mes", json={"periodo_mes": "2026-12"})
    assert vacio.status_code == 201
    assert vacio.json() == {"periodo": "2026-12", "creadas": 0, "ya_existentes": 0}

    # Crear 2 clientes recurrentes
    client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "JURIDICA",
            "nombre_razon_social": "Alpha S.A.S.",
            "documento_nit": "900111222-1",
            "es_recurrente": True,
        },
    )
    client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "NATURAL",
            "nombre_razon_social": "Carlos Ruiz",
            "documento_nit": "80111222",
            "es_recurrente": True,
        },
    )

    # Apertura idempotente
    init1 = client.post("/api/v1/cuentas/iniciar-mes", json={"periodo_mes": "2026-12"})
    assert init1.json()["creadas"] == 2
    init2 = client.post("/api/v1/cuentas/iniciar-mes", json={"periodo_mes": "2026-12"})
    assert init2.json()["creadas"] == 0
    assert init2.json()["ya_existentes"] == 2

    tablero = client.get("/api/v1/tablero/2026-12").json()
    cuenta1_id = tablero["cuentas_del_mes"][0]["id"]
    cuenta2_id = tablero["cuentas_del_mes"][1]["id"]

    # No se puede marcar como pagado un BORRADOR
    pago_borrador = client.patch(
        f"/api/v1/cuentas/{cuenta1_id}/pago",
        json={"pagada": True, "fecha_pago": "2026-12-10"},
    )
    assert pago_borrador.status_code == 400

    # No se puede emitir con valor 0 o concepto vacío
    emit_invalido = client.put(
        f"/api/v1/cuentas/{cuenta1_id}/emitir",
        json={
            "fecha_emision": "2026-12-05",
            "concepto_honorarios": "   ",
            "valor_total": "0.00",
        },
    )
    assert emit_invalido.status_code == 422

    # Emitir ambas cuentas -> consecutivos secuenciales
    emit1 = client.put(
        f"/api/v1/cuentas/{cuenta1_id}/emitir",
        json={
            "fecha_emision": "2026-12-05",
            "concepto_honorarios": "Servicios de arquitectura",
            "valor_total": "3000000.00",
        },
    )
    assert emit1.status_code == 200
    assert emit1.json()["consecutivo"] == "CC-2026-0001"
    ruta_pdf_1 = Path(emit1.json()["ruta_pdf"])
    assert ruta_pdf_1.is_file()

    emit2 = client.put(
        f"/api/v1/cuentas/{cuenta2_id}/emitir",
        json={
            "fecha_emision": "2026-12-06",
            "concepto_honorarios": "Consultoría técnica",
            "valor_total": "2000000.00",
        },
    )
    assert emit2.status_code == 200
    assert emit2.json()["consecutivo"] == "CC-2026-0002"

    # Editar cuenta 1 cambiando fecha a otro mes/año limpia el PDF huérfano anterior
    edit1 = client.put(
        f"/api/v1/cuentas/{cuenta1_id}/emitir",
        json={
            "fecha_emision": "2026-11-28",
            "concepto_honorarios": "Servicios de arquitectura (corregido)",
            "valor_total": "3200000.00",
        },
    )
    assert edit1.status_code == 200
    nueva_ruta_1 = Path(edit1.json()["ruta_pdf"])
    assert nueva_ruta_1.is_file()
    assert nueva_ruta_1 != ruta_pdf_1
    assert not ruta_pdf_1.exists()

    # Bloqueo de borrado físico en cuentas emitidas
    del_emitida = client.delete(f"/api/v1/cuentas/{cuenta1_id}")
    assert del_emitida.status_code == 400

    # Tachar como pagada y luego revertir
    pagar = client.patch(
        f"/api/v1/cuentas/{cuenta1_id}/pago",
        json={"pagada": True, "fecha_pago": "2026-12-15"},
    )
    assert pagar.status_code == 200
    assert pagar.json()["estado"] == "PAGADA"

    revertir = client.patch(
        f"/api/v1/cuentas/{cuenta1_id}/pago",
        json={"pagada": False},
    )
    assert revertir.status_code == 200
    assert revertir.json()["estado"] == "EMITIDA"
    assert revertir.json()["fecha_pago"] is None


# ---------------------------------------------------------------------------
# 4. Motor PDF, Conversión Monetaria y Resiliencia de Anexos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("0"), "CERO PESOS M/CTE"),
        (Decimal("1"), "UN PESO M/CTE"),
        (Decimal("1000000"), "UN MILLÓN DE PESOS M/CTE"),
        (Decimal("2540300"), "DOS MILLONES QUINIENTOS CUARENTA MIL TRESCIENTOS PESOS M/CTE"),
        (Decimal("1000001"), "UN MILLÓN UN PESOS M/CTE"),
    ],
)
def test_e2e_monto_a_letras_cop(valor: Decimal, esperado: str) -> None:
    """Valida reglas gramaticales colombianas para casos borde monetarios."""
    assert monto_a_letras_cop(valor) == esperado


def test_e2e_sanitizacion_pdf_anexos_y_resiliencia(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Valida sanitización, fusión pypdf de anexos y resiliencia si falta un anexo."""
    assert sanitizar_nombre_archivo("Constructora Andes S.A.S.") == "Constructora_Andes_SAS"

    # Subir firma y ambos anexos
    client.post(
        "/api/v1/emisor/archivos/firma",
        files={"file": ("firma.png", _crear_png_1x1_bytes(), "image/png")},
    )
    resp_rut = client.post(
        "/api/v1/emisor/archivos/rut",
        files={"file": ("rut.pdf", _crear_pdf_dummy_bytes(1), "application/pdf")},
    )
    resp_cert = client.post(
        "/api/v1/emisor/archivos/cert_bancaria",
        files={"file": ("cert.pdf", _crear_pdf_dummy_bytes(2), "application/pdf")},
    )
    cert_path = Path(resp_cert.json()["ruta_cert_bancaria_pdf"])
    assert Path(resp_rut.json()["ruta_rut_pdf"]).is_file()

    cli = client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "JURIDICA",
            "nombre_razon_social": "Empresa / Anexos & Cía S.A.S.",
            "documento_nit": "900777888-9",
        },
    ).json()

    cuenta = client.post(
        "/api/v1/cuentas/manual",
        json={
            "cliente_id": cli["id"],
            "periodo_mes": "2026-12",
            "estado": "EMITIDA",
            "fecha_emision": "2026-12-18",
            "concepto_honorarios": "Servicios de ingeniería\nLínea 2",
            "valor_total": "2540300.00",
        },
    ).json()

    pdf_completo = client.get(f"/api/v1/cuentas/{cuenta['id']}/pdf")
    assert pdf_completo.status_code == 200
    assert pdf_completo.content.startswith(b"%PDF-")
    paginas_con_anexos = len(PdfReader(io.BytesIO(pdf_completo.content)).pages)
    assert paginas_con_anexos >= 4

    # Borrar certificación bancaria del disco y regenerar -> no crashea y registra warning
    cert_path.unlink()
    with caplog.at_level(logging.WARNING):
        pdf_resiliente = client.get(
            f"/api/v1/cuentas/{cuenta['id']}/pdf?regenerar=true"
        )
    assert pdf_resiliente.status_code == 200
    assert "no existe en disco" in caplog.text
    paginas_sin_cert = len(PdfReader(io.BytesIO(pdf_resiliente.content)).pages)
    assert paginas_sin_cert == paginas_con_anexos - 2


# ---------------------------------------------------------------------------
# 5. Radar de Cartera Vencida (Mora)
# ---------------------------------------------------------------------------


def test_e2e_radar_cartera_vencida_y_kpis(client: TestClient) -> None:
    """Verifica detección de cuentas EMITIDA de meses anteriores y suma en KPIs."""
    cli = client.post(
        "/api/v1/clientes",
        json={
            "tipo_persona": "JURIDICA",
            "nombre_razon_social": "Mora Histórica S.A.S.",
            "documento_nit": "900555444-3",
        },
    ).json()

    client.post(
        "/api/v1/cuentas/manual",
        json={
            "cliente_id": cli["id"],
            "periodo_mes": "2026-10",
            "estado": "EMITIDA",
            "fecha_emision": "2026-10-05",
            "concepto_honorarios": "Honorarios octubre",
            "valor_total": "1500000.00",
        },
    )
    client.post(
        "/api/v1/cuentas/manual",
        json={
            "cliente_id": cli["id"],
            "periodo_mes": "2026-11",
            "estado": "EMITIDA",
            "fecha_emision": "2026-11-05",
            "concepto_honorarios": "Honorarios noviembre",
            "valor_total": "2000000.00",
        },
    )
    client.post(
        "/api/v1/cuentas/manual",
        json={
            "cliente_id": cli["id"],
            "periodo_mes": "2026-12",
            "estado": "EMITIDA",
            "fecha_emision": "2026-12-05",
            "concepto_honorarios": "Honorarios diciembre",
            "valor_total": "2500000.00",
        },
    )

    tablero = client.get("/api/v1/tablero/2026-12").json()
    assert len(tablero["cartera_vencida"]) == 2
    assert [c["periodo_mes"] for c in tablero["cartera_vencida"]] == ["2026-10", "2026-11"]
    assert Decimal(tablero["kpis"]["total_cartera_vencida_historica"]) == Decimal("3500000.00")
    assert Decimal(tablero["kpis"]["total_por_cobrar_mes"]) == Decimal("2500000.00")


# ---------------------------------------------------------------------------
# 6. Respaldo y Salud del Sistema
# ---------------------------------------------------------------------------


def test_e2e_respaldo_sqlite_retencion_y_salud(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida integridad de sqlite3.backup(), retención máxima de 30 archivos y /health."""
    resp_health = client.get("/api/v1/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "ok"

    db_path = tmp_path / "cobros.db"
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)")
    conn.execute("INSERT INTO clientes (nombre) VALUES ('Cliente Backup S.A.S.')")
    conn.commit()
    conn.close()

    # Simular 33 respaldos previos para verificar retención de últimos 30
    tiempo_base = time.time() - 1000
    previos: list[Path] = []
    for i in range(33):
        f = backups_dir / f"cobros_backup_2026-01-{i + 1:02d}_08-00.db"
        f.write_bytes(b"SQLite format 3\x00")
        mtime = tiempo_base + i
        os.utime(f, (mtime, mtime))
        previos.append(f)

    monkeypatch.setattr(backup_service.settings, "DB_PATH", db_path)
    monkeypatch.setattr(backup_service.settings, "BACKUPS_DIR", backups_dir)

    resp_backup = client.post("/api/v1/sistema/backup")
    assert resp_backup.status_code == 200
    ruta_backup = Path(resp_backup.json()["ruta"])
    assert ruta_backup.is_file()

    # Verificar integridad SQLite del backup
    conn_bk = sqlite3.connect(str(ruta_backup))
    filas = conn_bk.execute("SELECT nombre FROM clientes").fetchall()
    conn_bk.close()
    assert filas == [("Cliente Backup S.A.S.",)]

    # Verificar retención estricta de 30 archivos
    restantes = list(backups_dir.glob("cobros_backup_*.db"))
    assert len(restantes) == 30
    for eliminado in previos[:4]:
        assert not eliminado.exists()

    with pytest.raises(BusinessRuleException):
        backup_service.crear_respaldo_seguro(
            db_path=tmp_path / "no_existe.db",
            backups_dir=backups_dir,
        )
