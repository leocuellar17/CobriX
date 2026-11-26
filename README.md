# CobriX — Sistema de Gestión de Cuentas de Cobro y Control de Cartera

Aplicación de escritorio local (Windows) diseñada para profesionales independientes en Colombia. Permite administrar clientes (personas naturales y jurídicas), automatizar la apertura mensual de cobros estilo *To-Do List*, redactar honorarios dinámicos, generar documentos PDF formales con validez contable (incluyendo firma digitalizada y fusión automática de RUT y Certificación Bancaria), vigilar cartera vencida de meses anteriores y realizar respaldos transaccionales automáticos de la base de datos.

---

## Características Principales

- **Tablero Mensual Estilo To-Do List:** Apertura idempotente de mes para clientes recurrentes, filtros por estado (`Por Redactar`, `Por Cobrar`, `Pagadas`), tachado animado de pagos y KPIs financieros exactos en pesos colombianos (`Decimal`).
- **Radar de Cartera Vencida:** Alerta visual automática de cuentas emitidas en meses anteriores que aún no han sido pagadas, con acceso directo al PDF y registro de pago inmediato.
- **Motor Documental PDF (Colombia):**
  - Plantilla ejecutiva tamaño Carta (`Letter`) con notas legales colombianas (Art. 437 Parágrafo 3 E.T. y Art. 383 E.T.).
  - Conversión exacta de montos `Decimal` a letras en español colombiano (`num2words`).
  - Incrustación de firma escaneada en Base64 y fusión automática de **RUT** y **Certificación Bancaria** mediante `pypdf`.
  - Organización automática en disco por `Año / MM_NombreMes`.
- **Interfaz Web Local (Fluent 2 + Claymorfismo):** HTML5 + Tailwind CSS + Alpine.js v3 + Lucide Icons, servida directamente por FastAPI sin requerir Node.js en la máquina del usuario.
- **Despliegue "Cero Consola" en Windows:** Lanzador de instancia única en `127.0.0.1:8765`, bandeja del sistema (*System Tray*), logs rotativos y copias de seguridad automáticas con `sqlite3.Connection.backup()` (retención de los últimos 30 respaldos).

---

## Arquitectura del Sistema y Stack Tecnológico

```text
+-------------------------------------------------------------------+
|  UI Web Local (HTML5 + Tailwind + Alpine.js v3 + Fluent-Clay CSS) |
+---------------------------------+---------------------------------+
                                  | HTTP/JSON (127.0.0.1:8765/api/v1)
+---------------------------------v---------------------------------+
|  FastAPI Routers (app/api/routes.py) + Manejador de Excepciones   |
+---------------------------------+---------------------------------+
                                  |
+---------------------------------v---------------------------------+
|  Capa de Servicios:                                               |
|  - CobrosService (reglas de negocio, consecutivos, mora, KPIs)    |
|  - PDFService (Jinja2 + xhtml2pdf + pypdf + num2words)            |
|  - BackupService (sqlite3.backup() + retención 30 archivos)       |
+---------------------------------+---------------------------------+
                                  |
+---------------------------------v---------------------------------+
|  Repositorios CRUD Genéricos (BaseRepository[ModelType])          |
|  - EmisorRepository | ClienteRepository | CuentaCobroRepository   |
+---------------------------------+---------------------------------+
                                  | SQLAlchemy 2.0 (WAL + FK ON)
+---------------------------------v---------------------------------+
|  SQLite (cobros.db) + Almacenamiento Local en Documentos          |
+-------------------------------------------------------------------+
```

### Estructura de Carpetas

```text
sistema_cuentas_cobro/
├── launcher.py                      # Orquestador sin consola: instancia única, backup, tray y navegador
├── build_windows.spec               # Especificación PyInstaller (--onedir, --noconsole)
├── requirements.txt                 # Dependencias Python del proyecto
├── assets/
│   └── icono.ico                    # Ícono multi-resolución generado con Pillow
├── scripts/
│   ├── generar_icono.py             # Generador del ícono Fluent azul
│   ├── instalar_acceso_directo.ps1  # Crea acceso directo "Cuentas de Cobro" en el Escritorio
│   ├── iniciar_modo_dev.bat         # Lanzador silencioso en modo desarrollo
│   └── iniciar_silencioso.vbs       # Ejecución de pythonw.exe sin ventana de consola
├── app/
│   ├── main.py                      # Punto de entrada FastAPI, CORS, Lifespan, StaticFiles
│   ├── core/
│   │   ├── config.py                # Resolución BUNDLE_DIR vs USER_DATA_DIR
│   │   ├── exceptions.py            # Excepciones de negocio y handlers JSON
│   │   └── utils.py                 # Formateo COP, monto_a_letras_cop, sanitización y periodos
│   ├── db/
│   │   └── database.py              # Engine SQLite (WAL, foreign_keys=ON, busy_timeout)
│   ├── models/
│   │   └── domain.py                # Modelos ORM: Emisor, Cliente, CuentaCobro + Enums
│   ├── repositories/
│   │   ├── base.py                  # BaseRepository[ModelType] genérico
│   │   └── cobros_repository.py     # EmisorRepository, ClienteRepository, CuentaCobroRepository
│   ├── schemas/
│   │   └── schemas.py               # Esquemas Pydantic v2 y validaciones
│   ├── services/
│   │   ├── cobros_service.py        # Lógica de negocio y orquestación
│   │   ├── pdf_service.py           # Motor HTML -> PDF y fusión de anexos
│   │   └── backup_service.py        # Respaldo transaccional SQLite y rotación
│   ├── api/
│   │   └── routes.py                # Endpoints RESTful /api/v1/*
│   ├── static/
│   │   ├── css/fluent-clay.css      # Sistema de diseño Fluent 2 + Claymorfismo
│   │   └── js/                      # api.js, utils.js, app.js
│   └── templates/
│       ├── index.html               # Interfaz principal de usuario
│       └── cuenta_cobro.html        # Plantilla PDF tamaño Carta
└── tests/
    ├── conftest.py                  # Fixtures aislados (SQLite en memoria, tmp_path, TestClient)
    └── test_suite_e2e.py            # Suite E2E unificada y parametrizada
```

### Separación `BUNDLE_DIR` vs `USER_DATA_DIR`

- **`BUNDLE_DIR`**: En desarrollo apunta a la raíz del proyecto; cuando se compila con PyInstaller apunta a `sys._MEIPASS`. Contiene únicamente recursos de solo lectura (`app/templates/`, `app/static/`, `assets/`).
- **`USER_DATA_DIR`**: Apunta por defecto a `Documentos\Cuentas_de_Cobro\` (o a la carpeta junto al `.exe` si existe un archivo `portable.flag`). Allí se guardan de forma permanente:
  - `cobros.db` (base de datos SQLite)
  - `archivos\assets\` (firma digitalizada, RUT y certificación bancaria)
  - `backups\` (copias de seguridad automáticas)
  - `logs\app.log` (registro rotativo de eventos)
- **`OUTPUT_PDF_DIR`**: Los PDFs generados se guardan en la carpeta **Descargas** del usuario: `Descargas\CobriX_Cuentas\{Año}\{MM}_{Mes}\`, para que puedas moverlos a donde quieras.

---

## Requisitos Previos e Instalación en Entorno de Desarrollo

- **Python 3.11 o superior** (probado en Python 3.13.5 en Windows).

```powershell
# 1. Ingresar a la carpeta del proyecto
cd sistema_cuentas_cobro

# 2. Crear y activar entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar suite completa de pruebas E2E
pytest -v

# 5. Levantar servidor en modo desarrollo (recarga automática)
uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

---

## Compilación y Empaquetado para Windows (Modo Producción Cero Consola)

```powershell
# 1. Generar el ícono multi-resolución (assets/icono.ico)
python scripts/generar_icono.py

# 2. Compilar el ejecutable (--onedir, sin ventana de consola)
pyinstaller build_windows.spec

# 3. Crear el acceso directo "Cuentas de Cobro" en el Escritorio
powershell -ExecutionPolicy Bypass -File scripts/instalar_acceso_directo.ps1
```

El paquete final queda en `dist\CuentasDeCobro\CuentasDeCobro.exe`.

---

## Guía Rápida de Uso para el Usuario Final

1. **Abrir el programa:** Haz doble clic en el ícono **Cuentas de Cobro** en tu Escritorio. Se abrirá la aplicación en tu navegador y aparecerá un ícono azul en la bandeja del sistema (junto al reloj de Windows).
2. **Configuración inicial (una sola vez):** Ve a la pestaña **Mis Datos y Documentos**, completa tu nombre, C.C., RUT, datos bancarios y sube tu **Firma Escaneada** (`.png`/`.jpg`), **RUT** (`.pdf`) y **Certificación Bancaria** (`.pdf`).
3. **Registrar clientes:** En **Directorio de Clientes**, agrega tus empresas (NIT) o personas naturales (C.C.) y activa el interruptor **Recurrente mensual** para quienes cobras cada mes.
4. **Iniciar cada mes:** En **Tablero Mensual**, haz clic en **Iniciar Mes / Cargar Clientes Recurrentes**. Se creará tu lista de tareas pendientes en borrador.
5. **Redactar honorarios y generar PDF:** Haz clic en **Redactar Honorarios**, ingresa el valor (verás la vista previa en pesos), escribe el concepto (puedes copiar el del mes pasado con un clic) y presiona **Guardar y Generar PDF**.
6. **Tachar pagos y revisar mora:** Cuando recibas la transferencia, marca el checkbox grande a la izquierda del cliente. Si quedaron cuentas sin pagar de meses pasados, aparecerán automáticamente en la banda coral superior.
7. **Dónde encontrar tus archivos:** Todos tus PDFs quedan organizados en tu carpeta **Descargas** → `CobriX_Cuentas\{Año}\{Mes}\`, listos para que los muevas a donde desees. Las copias de seguridad de la BD están en `Documentos\Cuentas_de_Cobro\backups\`. También puedes usar el botón **Abrir Carpeta de PDFs** en la barra superior.

---

## Solución de Problemas Frecuentes (Troubleshooting)

- **El puerto `8765` está ocupado por otro programa:** Cierra cualquier instancia previa desde el ícono de la bandeja del sistema (*Cerrar Programa*) o verifica los procesos de Python en el Administrador de tareas.
- **Cómo restaurar una copia de seguridad:**
  1. Cierra la aplicación desde el botón **Cerrar App** o desde la bandeja del sistema.
  2. Ve a `Documentos\Cuentas_de_Cobro\backups\` y elige el archivo `cobros_backup_YYYY-MM-DD_HH-MM.db` deseado.
  3. Cópialo a `Documentos\Cuentas_de_Cobro\cobros.db` (reemplazando el archivo actual, previo respaldo manual).
  4. Vuelve a abrir **Cuentas de Cobro**.
- **Dónde revisar errores técnicos:** Consulta el archivo rotativo `Documentos\Cuentas_de_Cobro\logs\app.log`.

---

## Cómo Compartir / Instalar en Otro PC

### Opción A — Modo Desarrollo (requiere Python instalado)

1. Copia toda la carpeta `sistema_cuentas_cobro\` al otro PC (USB, OneDrive, etc.).
2. Instala [Python 3.11+](https://www.python.org/downloads/) marcando **"Add Python to PATH"**.
3. Abre PowerShell **en la carpeta del proyecto** y ejecuta:
   ```powershell
   pip install -r requirements.txt
   ```
4. Haz doble clic en **`CobriX - Cuentas de Cobro.bat`** para abrir la aplicación.
5. *(Opcional)* Clic derecho sobre el `.bat` → **Enviar a** → **Escritorio (crear acceso directo)**, y renómbralo a `CobriX`.

### Opción B — Ejecutable Compilado (no requiere Python)

1. En tu PC (donde ya tienes Python), abre PowerShell en la carpeta del proyecto y ejecuta:
   ```powershell
   pip install pyinstaller
   pyinstaller build_windows.spec
   ```
2. Se generará la carpeta `dist\CuentasDeCobro\` con el ejecutable `CuentasDeCobro.exe`.
3. Copia **toda la carpeta** `dist\CuentasDeCobro\` al otro PC (USB, OneDrive, etc.).
4. En el otro PC, haz doble clic en `CuentasDeCobro.exe`. ¡Listo, no se necesita instalar nada!
