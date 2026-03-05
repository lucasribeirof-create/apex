@echo off
title APEX Manager — Frontend
chcp 65001 > nul

if exist "C:\Program Files\nodejs\npm.cmd" set "PATH=C:\Program Files\nodejs;%PATH%"

echo.
echo  APEX Manager — Modo Desenvolvimento
echo  Backend gerenciado pelo Cursor (porta 8000)
echo  Frontend iniciando em http://localhost:3000
echo.

:: ── Abrir browser ─────────────────────────────────────────────────────────
start "" "http://localhost:3000"

:: ── Frontend nesta janela ─────────────────────────────────────────────────
cd /d %~dp0frontend
if not exist node_modules (
    echo Instalando dependencias do frontend... isso so acontece uma vez.
    npm install
)
npm run dev
