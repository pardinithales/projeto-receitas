@echo off
rem =====================================================
rem  Sistema de Receitas - basta dar 2 cliques neste arquivo
rem  (deixe esta janela aberta enquanto usa o sistema)
rem =====================================================
title Sistema de Receitas - NAO FECHE ESTA JANELA
cd /d "%~dp0"

rem instala dependencias na primeira vez (rapido quando ja instaladas)
python -m pip install -r requirements.txt --quiet --disable-pip-version-check

rem abre o navegador depois que o servidor subir
start /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8477"

echo.
echo  Sistema de Receitas iniciando em http://localhost:8477
echo  Para encerrar, feche esta janela.
echo.
python -m uvicorn app.main:app --port 8477
pause
