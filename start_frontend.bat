@echo off
title APEX Manager — Frontend

echo.
echo  ██████████████████████████████████████
echo     APEX MANAGER — Iniciando Frontend
echo  ██████████████████████████████████████
echo.

:: Adicionar Node.js ao PATH se necessário
if exist "C:\Program Files\nodejs\npm.cmd" (
    set "PATH=C:\Program Files\nodejs;%PATH%"
)

cd /d "%~dp0frontend"

:: Instalar dependências se node_modules não existir
if not exist "node_modules" (
    echo [INFO] Instalando dependencias Node.js...
    npm install
    echo.
)

echo [OK] App iniciando em http://localhost:3000
echo.
echo Para parar: Ctrl+C
echo.

npm run dev

pause
