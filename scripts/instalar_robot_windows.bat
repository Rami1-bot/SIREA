@echo off
REM ============================================================
REM SIREA · Instala el robot de actividad en el Programador de tareas de Windows.
REM Doble clic una vez. Crea la tarea "SIREA - mantener activo" que corre todos los dias
REM a las 08:30 y, si la PC estaba apagada a esa hora, apenas se encienda.
REM Para quitarla:  schtasks /Delete /TN "SIREA - mantener activo" /F
REM ============================================================
setlocal
cd /d "%~dp0.."
set "RAIZ=%CD%"
if exist "%RAIZ%\venv\Scripts\python.exe" (
  set "PY=%RAIZ%\venv\Scripts\python.exe"
) else (
  set "PY=python"
)
if not exist "%RAIZ%\storage\logs" mkdir "%RAIZ%\storage\logs"

echo Probando el robot una vez...
"%PY%" "%RAIZ%\scripts\mantener_activo.py" --detalle
echo.

schtasks /Create /F /TN "SIREA - mantener activo" /SC DAILY /ST 08:30 ^
  /TR "\"%PY%\" \"%RAIZ%\scripts\mantener_activo.py\"" >nul
if errorlevel 1 (
  echo No se pudo crear la tarea. Ejecute este archivo con clic derecho - "Ejecutar como administrador".
  pause
  exit /b 1
)
REM Que se ejecute al encender si se perdio la hora programada
powershell -NoProfile -Command "$t=Get-ScheduledTask -TaskName 'SIREA - mantener activo'; $t.Settings.StartWhenAvailable=$true; Set-ScheduledTask -InputObject $t | Out-Null" 2>nul

echo Listo: la tarea "SIREA - mantener activo" corre todos los dias a las 08:30.
echo El resultado de cada revision queda en storage\logs\mantener_activo.log
pause
