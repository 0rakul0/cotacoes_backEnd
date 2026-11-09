@echo off
setlocal EnableExtensions
rem Executa o FastAPI com caminhos relativos ao repositorio.
rem Uso: start_cotacoes.cmd
rem Para uso local, escuta somente em 127.0.0.1:7777.

cd /d "%~dp0..\.." || exit /b 2
if not exist ".venv\Scripts\python.exe" (
    echo ERRO: Python virtual nao encontrado em .venv\Scripts\python.exe 1>&2
    exit /b 2
)
if not exist "data\logs" mkdir "data\logs"
echo [%date% %time%] Iniciando Cotacoes FastAPI >> "data\logs\cotacoes-windows.log"
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 7777 --no-access-log >> "data\logs\cotacoes-windows.log" 2>&1
set "exitcode=%errorlevel%"
echo [%date% %time%] Processo encerrado com codigo %exitcode% >> "data\logs\cotacoes-windows.log"
exit /b %exitcode%
