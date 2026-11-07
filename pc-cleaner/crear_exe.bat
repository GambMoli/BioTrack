@echo off
rem Crea dist\LimpiaPC.exe (un solo archivo, no necesita Python para ejecutarse).
cd /d "%~dp0"
set PY=py
where py >nul 2>nul || set PY=python
%PY% -m pip install --upgrade pyinstaller || goto :error
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name LimpiaPC LimpiaPC.pyw || goto :error
echo.
echo  Listo: dist\LimpiaPC.exe
echo.
pause
exit /b 0

:error
echo.
echo  Algo fallo creando el .exe. Revisa los mensajes de arriba.
echo.
pause
exit /b 1
