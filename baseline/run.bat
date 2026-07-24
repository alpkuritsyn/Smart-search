@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Освобождаю порт (если старый процесс остался активным)...
powershell -Command "$port=8080; if(Test-Path .env){Get-Content .env|%%{if($_ -match '^\s*PORT\s*=\s*(\d+)'){$port=$Matches[1]}}}; $conn=Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue; if($conn){Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue}"
echo Запуск сайта и чат-бота...
echo.

set "UV_PYTHON=%APPDATA%\uv\python\cpython-3.12-windows-x86_64-none\python.exe"
if exist "%UV_PYTHON%" goto managed_python

where uv >nul 2>nul
if not errorlevel 1 goto uv_python

where python >nul 2>nul
if not errorlevel 1 goto system_python
goto no_python

:managed_python
"%UV_PYTHON%" -u server.py
goto finished

:uv_python
uv run --python 3.12 --no-project python -u server.py
goto finished

:system_python
python -u server.py
goto finished

:no_python
echo Python не найден. Выполните: uv python install 3.12
pause
exit /b 1

:finished
if errorlevel 1 pause
