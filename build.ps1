# Construye el ejecutable de Windows en dist\MundoPTAL\MundoPTAL.exe
# y un .zip listo para copiar a cualquier ordenador del colegio.
# Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Modelo = "vosk-model-small-es-0.42"
$UrlModelo = "https://alphacephei.com/vosk/models/$Modelo.zip"

if (-not (Test-Path ".venv")) {
    Write-Host "Creando entorno virtual de Python..."
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

if (-not (Test-Path "models\$Modelo")) {
    Write-Host "Descargando el modelo de voz en español ($Modelo)..."
    New-Item -ItemType Directory -Force -Path models | Out-Null
    Invoke-WebRequest -Uri $UrlModelo -OutFile "models\$Modelo.zip"
    Expand-Archive -Path "models\$Modelo.zip" -DestinationPath models -Force
    Remove-Item "models\$Modelo.zip"
}

Write-Host "Ejecutando pruebas..."
& .\.venv\Scripts\python.exe -m pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "Las pruebas han fallado" }

Write-Host "Empaquetando con PyInstaller..."
& .\.venv\Scripts\pyinstaller.exe --noconfirm MundoPTAL.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado" }

$Zip = "dist\MundoPTAL-windows.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path "dist\MundoPTAL" -DestinationPath $Zip
Write-Host ""
Write-Host "Listo: dist\MundoPTAL\MundoPTAL.exe  y  $Zip"
