$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExePath = Join-Path $ProjectRoot "dist\CuentasDeCobro\CuentasDeCobro.exe"
$IconPath = Join-Path $ProjectRoot "assets\icono.ico"

if (-not (Test-Path $ExePath)) {
    Write-Error "No se encontró el ejecutable en '$ExePath'. Ejecuta primero: pyinstaller build_windows.spec"
    exit 1
}

$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "Cuentas de Cobro.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = Split-Path -Parent $ExePath
$Shortcut.Description = "Gestión Autónoma de Cuentas de Cobro y Cartera"
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
}
$Shortcut.Save()

Write-Host "Acceso directo creado exitosamente en: $ShortcutPath" -ForegroundColor Green
