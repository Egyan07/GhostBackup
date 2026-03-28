@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ============================================
echo   GhostBackup Setup
echo  ============================================
echo.

REM ── Python check ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Download Python 3.10 or newer from https://python.org
    echo  Make sure to tick "Add Python to PATH" during installation.
    pause & exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1 delims=." %%a in ("!PYVER!") do set PYMAJ=%%a
for /f "tokens=2 delims=." %%b in ("!PYVER!") do set PYMIN=%%b

if !PYMAJ! LSS 3 goto :py_old
if !PYMAJ! EQU 3 if !PYMIN! LSS 10 goto :py_old
echo  [OK] Python !PYVER!
goto :py_ok

:py_old
echo  [ERROR] Python 3.10 or newer required ^(found !PYVER!^).
echo  Download from https://python.org
pause & exit /b 1

:py_ok

REM ── Node.js check ─────────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js not found.
    echo  Download Node.js 18 or newer from https://nodejs.org
    pause & exit /b 1
)

for /f "tokens=* delims=v" %%v in ('node --version') do set NODEVER=%%v
for /f "tokens=1 delims=." %%a in ("!NODEVER!") do set NODEMAJ=%%a
if !NODEMAJ! LSS 18 (
    echo  [ERROR] Node.js 18 or newer required ^(found v!NODEVER!^).
    echo  Download from https://nodejs.org
    pause & exit /b 1
)
echo  [OK] Node.js v!NODEVER!
echo.

REM ── Step 1: Python virtual environment ────────────────────────────────────
echo  [1/4] Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo  [ERROR] Failed to create virtual environment.
    pause & exit /b 1
)

REM ── Step 2: Python packages ────────────────────────────────────────────────
echo  [2/4] Installing Python packages ^(this may take a minute^)...
call .venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check your internet connection and try again.
    pause & exit /b 1
)

REM ── Step 3: Node packages ─────────────────────────────────────────────────
echo  [3/4] Installing Node packages...
call npm ci --silent
if errorlevel 1 (
    echo  [ERROR] npm install failed. Check your internet connection and try again.
    pause & exit /b 1
)

REM ── Step 4: Configure paths and generate encryption key ───────────────────
echo  [4/4] Configuring GhostBackup...
echo.
python backend\setup_helper.py
if errorlevel 1 (
    echo  [ERROR] Configuration failed. See the error above.
    pause & exit /b 1
)

REM ── Create start.bat ──────────────────────────────────────────────────────
if exist start.bat (
    echo  [SKIP] start.bat already exists — not overwriting.
) else (
    (
        echo @echo off
        echo call .venv\Scripts\activate.bat
        echo npm run dev
    ) > start.bat
)

echo.
echo  ============================================
echo   Installation complete!
echo  ============================================
echo.
echo   Double-click start.bat to launch GhostBackup.
echo.
pause
