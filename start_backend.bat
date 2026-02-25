@echo off
title APEX Manager — Backend

echo.
echo  ██████████████████████████████████████
echo     APEX MANAGER — Iniciando Backend
echo  ██████████████████████████████████████
echo.

cd /d "%~dp0backend"

:: Verificar se o .env existe
if not exist "..\env" (
    if not exist "..\.env" (
        echo [AVISO] Arquivo .env nao encontrado.
        echo Copie .env.example para .env e preencha sua ANTHROPIC_API_KEY
        echo.
        pause
        exit /b 1
    )
)

:: Verificar se o ambiente virtual existe
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Criando ambiente virtual Python...
    python -m venv venv
    echo.
)

:: Ativar ambiente virtual
call venv\Scripts\activate.bat

:: Instalar dependências se necessário
echo [INFO] Verificando dependencias...
pip install -r requirements.txt -q

echo.
echo [OK] Servidor iniciando em http://localhost:8000
echo [OK] Documentacao da API: http://localhost:8000/docs
echo.
echo Para parar o servidor: Ctrl+C
echo.

:: Iniciar servidor
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

pause
