# -*- mode: python ; coding: utf-8 -*-
# Empaquetado del ejecutable de Windows:  pyinstaller --noconfirm MundoPTAL.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = [("mundoptal/static", "static")]
binaries = []
hiddenimports = []

# Modelo de voz en español (lo descarga build.ps1 en la carpeta models/)
if Path("models").exists():
    datas.append(("models", "models"))

for paquete in ("vosk", "_sounddevice_data", "webview", "docx", "openpyxl"):
    try:
        d, b, h = collect_all(paquete)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["MundoPTAL.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["sounddevice"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MundoPTAL",
    console=False,
    icon="mundoptal/static/icon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="MundoPTAL")
