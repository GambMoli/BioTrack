@echo off
rem Abre LimpiaPC sin ventana de consola.
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw -m limpiapc & exit /b)
where pythonw >nul 2>nul && (start "" pythonw -m limpiapc & exit /b)
echo.
echo  No se encontro Python.
echo  Instalalo desde https://www.python.org/downloads/
echo  (durante la instalacion marca "Add python.exe to PATH") y vuelve a abrir este archivo.
echo.
pause
