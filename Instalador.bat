@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Instalador OCT Workbench

echo ==========================================
echo OCT Workbench
echo Instalador de entorno y librerias
echo ==========================================
echo.

REM =====================================================
REM Buscar Python 3.12
REM =====================================================

py -3.12 --version >nul 2>&1

if errorlevel 1 (
    echo Python 3.12 no encontrado.
    echo.

    if not exist "installers\python-3.12.10-amd64.exe" (
        echo ERROR:
        echo No se encontro el instalador local de Python:
        echo installers\python-3.12.10-amd64.exe
        echo.
        echo Instala Python 3.12 manualmente y vuelve a ejecutar este archivo,
        echo o agrega el instalador oficial en la carpeta installers.
        pause
        exit /b 1
    )

    echo Instalando Python 3.12.10...
    start "Python 3.12" /wait "installers\python-3.12.10-amd64.exe" /passive InstallAllUsers=1 PrependPath=1

    echo.
    echo Reintentando deteccion...
    timeout /t 5 >nul

    py -3.12 --version >nul 2>&1

    if errorlevel 1 (
        echo.
        echo ERROR:
        echo No se pudo detectar Python 3.12 despues de la instalacion.
        pause
        exit /b 1
    )
)

echo Python 3.12 detectado.
py -3.12 --version
echo.

REM =====================================================
REM Crear entorno virtual
REM =====================================================

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    py -3.12 -m venv ".venv"

    if errorlevel 1 (
        echo.
        echo ERROR creando entorno virtual.
        pause
        exit /b 1
    )
) else (
    echo Entorno virtual existente encontrado.
)

echo.

REM =====================================================
REM Activar entorno virtual
REM =====================================================

call ".venv\Scripts\activate.bat"

if errorlevel 1 (
    echo.
    echo ERROR activando entorno virtual.
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo.
    echo ERROR: No se encontro requirements.txt en la carpeta del proyecto.
    pause
    exit /b 1
)

echo.
echo Configurando pip para redes institucionales...
set "PIP_TRUST=--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org"

echo.
echo Actualizando pip...
python -m pip install --upgrade pip %PIP_TRUST%

if errorlevel 1 (
    echo.
    echo ERROR actualizando pip.
    pause
    exit /b 1
)

echo.
echo Instalando dependencias desde requirements.txt...
python -m pip install -r requirements.txt %PIP_TRUST%

if errorlevel 1 (
    echo.
    echo ERROR instalando dependencias.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo Instalacion completada correctamente
echo ==========================================
echo.
echo Para ejecutar la GUI:
echo   .venv\Scripts\python.exe main.py
echo.
pause
endlocal
exit /b 0
