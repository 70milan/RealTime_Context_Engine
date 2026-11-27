@echo off
setlocal enabledelayedexpansion
echo ==========================================
echo   LOCAL BUILD (no publishing, no signing needed)
echo ==========================================
echo Builds the Windows installer on this PC. Nothing is uploaded anywhere and
echo the version number is not changed. For maintainers: build-all.bat signs
echo the build and publishes a GitHub release.
echo.

:: Prerequisites: Python 3.13+ and Node.js 20+
where python >nul 2>&1 || (echo [ERROR] Python is not installed or not on PATH & goto :fail)
where node >nul 2>&1 || (echo [ERROR] Node.js is not installed or not on PATH & goto :fail)

echo [1/2] Building the backend...
cd backend
if exist dist rmdir /s /q dist
if not exist ".venv-build\Scripts\python.exe" (
    echo [INFO] Creating the build environment backend\.venv-build ...
    python -m venv .venv-build || (echo [ERROR] Could not create the build environment & cd .. & goto :fail)
)
".venv-build\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo [ERROR] pip install failed & cd .. & goto :fail)
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm WinHostSvc.spec || (echo [ERROR] PyInstaller failed & cd .. & goto :fail)
cd ..

echo.
echo [2/2] Building the installer...
cd frontend
if not exist node_modules (
    echo [INFO] Installing frontend packages...
    call npm install || (echo [ERROR] npm install failed & cd .. & goto :fail)
)

:: The release build signs with the maintainer's certificate; local builds are unsigned
set "SIGN_ARGS="
if not exist "..\windows-runtime-host.pfx" set "SIGN_ARGS=-c.win.sign=scripts/skip-sign.js"

:: Calls electron-builder directly (not "npm run build", which bumps the version)
call npx electron-builder --publish never !SIGN_ARGS!
if %errorlevel% neq 0 (
    echo [ERROR] The installer build failed. Check the messages above.
    cd ..
    goto :fail
)
cd ..

echo.
echo ==========================================
echo   LOCAL BUILD COMPLETE
echo ==========================================
echo   Installer: frontend\dist\  (Windows-Runtime-Host-Setup-x.y.z.exe)
echo   It is unsigned, so Windows will show "Unknown publisher": More info, then Run anyway.
echo.
if not defined CI pause
exit /b 0

:fail
echo.
echo [BUILD FAILED]
if not defined CI pause
exit /b 1
