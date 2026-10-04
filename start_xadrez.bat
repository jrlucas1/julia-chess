@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"

rem Allow machine-specific locations and search depth to be overridden.
set "BRIDGE=%~dp0..\v04\jev-bot\bridge"
if not exist "%BRIDGE%\.venv-julia\Scripts\python.exe" set "BRIDGE=%~dp0..\bridge"
if not defined JULIA_PYTHON set "JULIA_PYTHON=%BRIDGE%\.venv-julia\Scripts\python.exe"
if not defined JULIA_MODEL_PATH set "JULIA_MODEL_PATH=%BRIDGE%\Julia-1"
if not defined JULIA_DEVICE set "JULIA_DEVICE=cuda"
if not defined CHESS_DEPTH set "CHESS_DEPTH=6"
if not defined CHESS_THINK_TIME set "CHESS_THINK_TIME=3.0"
if not defined CHESS_MARGIN set "CHESS_MARGIN=120"
if not defined CHESS_PORT set "CHESS_PORT=27600"
if not defined CHESS_JULIA_COLOR set "CHESS_JULIA_COLOR=black"
rem Bind to the LAN so a phone on the same Wi-Fi can watch the match.
if not defined CHESS_HOST set "CHESS_HOST=0.0.0.0"

if not exist "%JULIA_PYTHON%" (
  echo [chess] Julia Python environment not found:
  echo         %JULIA_PYTHON%
  echo Set JULIA_PYTHON to the Python executable in your Julia environment.
  exit /b 1
)
if not exist "%JULIA_MODEL_PATH%\julia\__init__.py" (
  echo [chess] Julia model package not found:
  echo         %JULIA_MODEL_PATH%
  echo Set JULIA_MODEL_PATH to the Julia-1 model directory.
  exit /b 1
)

"%JULIA_PYTHON%" -c "import chess" >nul 2>&1
if errorlevel 1 (
  echo [chess] Installing the chess rules dependency into the existing Julia environment...
  "%JULIA_PYTHON%" -m pip install -r "%~dp0requirements.txt"
  if errorlevel 1 (
    echo [chess] Dependency setup failed. Check your network connection and Python environment.
    exit /b 1
  )
)

"%JULIA_PYTHON%" -c "import torch; from julia import load_model" >nul 2>&1
if errorlevel 1 (
  echo [chess] Julia runtime dependencies are unavailable in this Python environment.
  echo Run the Julia setup script in the bridge folder, then retry:
  echo   %BRIDGE%\setup_julia.bat
  exit /b 1
)

echo [chess] Starting Julia Chess Lab. The server will print the phone URL below.
"%JULIA_PYTHON%" chess_server.py --julia-path "%JULIA_MODEL_PATH%" --device "%JULIA_DEVICE%" --host "%CHESS_HOST%" --port "%CHESS_PORT%" --julia-color "%CHESS_JULIA_COLOR%" --depth "%CHESS_DEPTH%" --think-time "%CHESS_THINK_TIME%" --margin "%CHESS_MARGIN%"
exit /b %errorlevel%
