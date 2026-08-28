@echo off
title Monitoreo de 22 Activos - Estrategias Cardona
echo ============================================================
echo   INICIANDO BOT DE MONITOREO AUTOMATICO (22 ACTIVOS)
echo ============================================================
echo.
echo [*] Buscando Python en el sistema...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] No se encontro Python instalado o no esta en el PATH del sistema.
    echo Por favor, instala Python y asegúrate de marcar la casilla "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b
)

echo [*] Ejecutando live_scanner.py con intervalo de 15 minutos...
echo [TIP] Puedes presionar Ctrl+C en cualquier momento para detener el bot.
echo.
python live_scanner.py --loop 15

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] El bot se detuvo con errores. Revisa los mensajes de arriba.
    echo.
    pause
)
