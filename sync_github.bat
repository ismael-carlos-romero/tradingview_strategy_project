@echo off
title 🐙 MELIORA OPTIONS - SINCRONIZADOR DE GITHUB 🐙
set "GIT_PATH=C:\Users\Ismael Romero\mingit\cmd\git.exe"

cd /d "C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project"

echo ===================================================
echo  MELIORA OPTIONS - SINCRONIZADOR DE GITHUB
echo ===================================================
echo.

:: 1. Limpiar cache local corrupta si existiera
if exist .git (
    echo [Git] Limpiando cache local anterior...
    rmdir /s /q .git
)

echo [Git] Habilitando soporte para rutas largas...
"%GIT_PATH%" config --global core.longpaths true

echo [Git] Configurando identidad del autor...
"%GIT_PATH%" config --global user.name "ismael-carlos-romero"
"%GIT_PATH%" config --global user.email "ismael.romero.dev@gmail.com"

echo [Git] Inicializando repositorio limpio...
"%GIT_PATH%" init
"%GIT_PATH%" branch -M main

echo [Git] Enlazando con el repositorio remoto...
"%GIT_PATH%" remote add origin "https://github.com/ismael-carlos-romero/tradingview_strategy_project.git"

echo [Git] Escaneando y agregando archivos de codigo locales...
"%GIT_PATH%" add -A

echo [Git] Creando commit local...
"%GIT_PATH%" commit -m "Actualizacion automatica Meliora Options"

echo.
echo [Git] Subiendo cambios a GitHub de forma forzada...
"%GIT_PATH%" push -f origin main

if errorlevel 1 (
    echo.
    echo ERROR: La subida fallo.
) else (
    echo.
    echo Repositorio de GitHub actualizado con exito!
)
echo.
timeout /t 5
