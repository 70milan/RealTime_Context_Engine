@echo off
echo ==========================================
echo       BUILDING INTERVIEW ASSISTANT
echo ==========================================

echo.

echo [1/2] Building Backend (PyInstaller)...
cd backend
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
pyinstaller interview-backend.spec
if %errorlevel% neq 0 (
    echo [ERROR] Backend build failed!
    pause
    exit /b %errorlevel%
)
echo.
echo [1.5/2] Signing Backend Executable...
if exist "..\windows-runtime-host.pfx" (
    signtool sign /f "..\windows-runtime-host.pfx" /p 1234 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 "dist\WinHostSvc.exe"
    if %errorlevel% neq 0 (
        echo [WARNING] Backend signing failed! Continuing anyway...
    ) else (
        echo [SUCCESS] Backend signed successfully.
    )
) else (
    echo [WARNING] No certificate found at ..\windows-runtime-host.pfx. Skipping signature.
)

cd ..
echo [SUCCESS] Backend built successfully.
echo.

echo [2/2] Building Frontend (Electron)...
cd frontend
call npm run build -- --publish always
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed!
    pause
    exit /b %errorlevel%
)
cd ..
echo.

echo ==========================================
echo [SUCCESS] ALL BUILDS COMPLETE!
echo Installer is located in: frontend/dist/
echo ==========================================
pause
