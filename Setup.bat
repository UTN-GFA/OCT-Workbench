@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual de OCT Workbench.
    echo Ejecuta Instalador.bat una vez para preparar el entorno.
    pause
    endlocal
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo No se pudo activar el entorno virtual.
    pause
    endlocal
    exit /b 1
)

python oct_workbench_gui.py
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
