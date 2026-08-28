@echo off
title 🚀 MELIORA OPTIONS - LANZADOR 🚀
cd /d "C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project"

echo ===================================================
echo 🚀 INICIANDO BOT Y PORTAL DE MELIORA OPTIONS 🚀
echo ===================================================
echo.

:: 1. Detener procesos anteriores de Python colgados para evitar conflictos
echo [Sistema] Limpiando procesos de fondo anteriores...
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: 2. Iniciar el bot de Python (live_scanner.py) en segundo plano
echo [Bot] Iniciando servidor del Bot en segundo plano...
start /min "Meliora Bot Server" python live_scanner.py

:: 3. Iniciar el gestor de tuneles (run_tunnel.py) en segundo plano
echo [Tunel] Iniciando tunel seguro de Serveo (para el celular)...
start /min "Meliora Tunnel Server" python run_tunnel.py

:: 4. Esperar a que el servidor local levante
echo [Sistema] Esperando 4 segundos a que se estabilicen las conexiones...
timeout /t 4 /nobreak >nul

:: 5. Abrir el portal en el navegador por defecto
echo [Portal] Abriendo portal local en tu navegador...
start http://127.0.0.1:8055

echo.
echo 🎉 ¡Meliora Options esta activo y corriendo en tu computadora!
echo.
echo [Nota] Las consolas de fondo de Python estan ejecutandose minimizadas.
echo Cuando termines de operar y quieras APAGAR el bot por completo, 
echo solo presiona cualquier tecla en esta ventana.
echo.
pause

:: Limpieza al salir si el usuario presiona una tecla
echo [Sistema] Apagando servidores y liberando puertos...
taskkill /f /im python.exe >nul 2>&1
echo [Sistema] Apagado completo. ¡Hasta pronto!
timeout /t 2 /nobreak >nul
