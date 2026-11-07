@echo off
setlocal
title Crear LimpiaPC.exe
cd /d "%~dp0"

echo.
echo  ==========================================
echo           Crear LimpiaPC.exe
echo  ==========================================
echo.

rem --- 1) Buscar Python (el atajo de la Microsoft Store no cuenta si no esta instalado) ---
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (python --version >nul 2>&1 && set "PY=python")
if not defined PY goto :sin_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || goto :python_viejo
%PY% -c "import tkinter" >nul 2>&1 || goto :sin_tk
for /f "delims=" %%v in ('%PY% --version') do echo  Usando %%v

rem --- 2) Entorno aislado para no tocar tu instalacion de Python ---
if not exist ".build-venv\Scripts\python.exe" (
    echo  Preparando el entorno de compilacion...
    %PY% -m venv .build-venv || goto :error
)
set "VPY=.build-venv\Scripts\python.exe"
echo  Instalando PyInstaller (la primera vez tarda un poco)...
"%VPY%" -m pip install --disable-pip-version-check --quiet --upgrade pyinstaller || goto :error

rem --- 3) Comprobar que la app abre bien (veras la ventana unos segundos) ---
echo  Comprobando que la app funciona...
"%VPY%" -m limpiapc --selftest
if errorlevel 1 (
    echo.
    echo  La comprobacion fallo. Detalles:
    type "%TEMP%\limpiapc-selftest.log"
    goto :error
)

rem --- 4) Crear el .exe (al abrirlo pedira permisos de administrador: los necesita para limpiar C:) ---
echo  Creando LimpiaPC.exe (1-2 minutos)...
"%VPY%" -m PyInstaller --noconfirm --clean --log-level WARN --onefile --windowed --uac-admin --icon limpiapc.ico --name LimpiaPC LimpiaPC.pyw || goto :error
if not exist "dist\LimpiaPC.exe" goto :error

echo.
echo  Listo:  %CD%\dist\LimpiaPC.exe
echo  Puedes copiarlo donde quieras, por ejemplo al Escritorio.
echo  La primera vez Windows puede avisar porque no esta firmado:
echo  "Mas informacion" y luego "Ejecutar de todas formas".
echo.
explorer "%CD%\dist"
pause
exit /b 0

:sin_python
echo  No se encontro Python.
echo  Instalalo desde https://www.python.org/downloads/
echo  (durante la instalacion marca "Add python.exe to PATH") y vuelve a abrir este archivo.
goto :fin_error

:python_viejo
echo  Tu Python es muy antiguo. Instala Python 3.9 o superior desde https://www.python.org/downloads/
goto :fin_error

:sin_tk
echo  A tu Python le falta tkinter (la parte grafica).
echo  Reinstala Python desde python.org dejando marcada la opcion "tcl/tk and IDLE".
goto :fin_error

:error
echo.
echo  Algo fallo. Revisa los mensajes de arriba.

:fin_error
echo.
pause
exit /b 1
