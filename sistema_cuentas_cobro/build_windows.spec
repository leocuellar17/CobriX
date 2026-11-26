# -*- mode: python ; coding: utf-8 -*-
"""Especificación PyInstaller (--onedir, --noconsole) para Cuentas de Cobro (CobriX)."""

from PyInstaller.utils.hooks import collect_all

datas = [
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
    ("assets/icono.ico", "assets"),
]
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "pystray._win32",
    "PIL._tkinter_finder",
    "multipart",
    "python_multipart",
    "app.repositories",
    "app.repositories.base",
    "app.repositories.cobros_repository",
]

for pkg in ("xhtml2pdf", "reportlab", "num2words", "pypdf", "jinja2"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]


a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CuentasDeCobro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icono.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CuentasDeCobro",
)
