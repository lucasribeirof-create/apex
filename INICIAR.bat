@echo off
title APEX Manager
chcp 65001 > nul

if exist "C:\Program Files\nodejs\npm.cmd" set "PATH=C:\Program Files\nodejs;%PATH%"

:: ── Backend em janela minimizada ─────────────────────────────────────────
start /min "APEX Backend" cmd /k "cd /d %~dp0backend && (if not exist venv\Scripts\activate.bat python -m venv venv) && call venv\Scripts\activate.bat && pip install -r requirements.txt -q && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app"

:: ── Abrir browser após delay (espera frontend + backend subirem) ────────
start /min "" cmd /c "timeout /t 14 /nobreak > nul && start "" http://localhost:3000"

:: ── Frontend nesta janela ─────────────────────────────────────────────────
cd /d %~dp0frontend
if not exist node_modules (
    echo Instalando dependencias do frontend... isso so acontece uma vez.
    npm install
)
echo.
echo  APEX Manager rodando em http://localhost:3000
echo  Backend minimizado na barra de tarefas (clique em "APEX Backend" para ver os logs)
echo  Feche esta janela para parar tudo.
echo.
npm run dev

