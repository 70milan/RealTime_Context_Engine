@echo off
setlocal enabledelayedexpansion
echo ==========================================
echo       BUILDING INTERVIEW ASSISTANT
echo ==========================================

:: 1. Check for GitHub Token
if "%GH_TOKEN%"=="" (
    echo [WARNING] GH_TOKEN environment variable is NOT detected.
    echo Since you currently have a terminal open, your system variables might not have synced yet.
    set /p "TOKEN_INPUT=Please paste your GitHub Token (ghp_...) here: "
    if "!TOKEN_INPUT!"=="" (
        echo [ERROR] No token provided. Publishing will fail.
        pause
        exit /b 1
    )
    :: Set it for this window session
    set "GH_TOKEN=!TOKEN_INPUT!"
)

:: 1b. Check for Certificate Password
if "%CSC_KEY_PASSWORD%"=="" (
    echo [WARNING] CSC_KEY_PASSWORD environment variable is NOT detected.
    set /p "CERT_PW_INPUT=Please enter your certificate password: "
    if "!CERT_PW_INPUT!"=="" (
        echo [ERROR] No certificate password provided. Code signing will fail.
        pause
        exit /b 1
    )
    set "CSC_KEY_PASSWORD=!CERT_PW_INPUT!"
)

:: 2. Find signtool.exe
echo [INFO] Locating signtool.exe...
set "SIGNTOOL_PATH="
for /f "delims=" %%i in ('where signtool 2^>nul') do set "SIGNTOOL_PATH=%%i"

if "%SIGNTOOL_PATH%"=="" (
    :: Search common Windows SDK paths
    set "SDK_ROOT=C:\Program Files (x86)\Windows Kits\10\bin"
    if exist "!SDK_ROOT!" (
        for /f "delims=" %%d in ('dir /b /ad "!SDK_ROOT!\10.*" 2^>nul') do (
            if exist "!SDK_ROOT!\%%d\x64\signtool.exe" (
                set "SIGNTOOL_PATH=!SDK_ROOT!\%%d\x64\signtool.exe"
            )
        )
    )
    :: Fallback to App Certification Kit
    if "!SIGNTOOL_PATH!"=="" (
        if exist "C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe" (
            set "SIGNTOOL_PATH=C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe"
        )
    )
)

if "!SIGNTOOL_PATH!"=="" (
    echo [WARNING] signtool.exe not found. Code signing will likely fail.
    echo To fix this, install the Windows SDK.
) else (
    echo [SUCCESS] Found signtool at: "!SIGNTOOL_PATH!"
    :: EXTRACT DIR AND ADD TO PATH so electron-builder can find it
    for %%F in ("!SIGNTOOL_PATH!") do set "SIGNTOOL_DIR=%%~dpF"
    set "PATH=!SIGNTOOL_DIR!;%PATH%"
    echo [INFO] Added signtool directory to PATH for this session.
)

echo.
echo [1/2] Building and Signing Backend...
cd backend
if exist dist rmdir /s /q dist
pyinstaller interview-backend.spec || (echo [ERROR] PyInstaller failed & pause & exit /b 1)

if not "!SIGNTOOL_PATH!"=="" (
    if exist "..\windows-runtime-host.pfx" (
        echo [INFO] Signing backend binary...
        signtool sign /f "..\windows-runtime-host.pfx" /p "!CSC_KEY_PASSWORD!" /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 "dist\WinHostSvc.exe"
    )
)
cd ..

echo.
echo [2/2] Building and Publishing Frontend...
cd frontend

:: Obfuscate
echo [INFO] Obfuscating code...
call npm run obfuscate || (echo [ERROR] Obfuscation failed & pause & exit /b 1)

:: Build and Publish
echo [INFO] Running Electron-Builder (Publishing to GitHub)...
:: Version check logic
for /f "tokens=*" %%i in ('node -p "require('./package.json').version"') do set "VERSION=%%i"

call npm run build -- --publish always
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Publishing failed! 
    echo Check for Authentication, Version Mismatch, or signtool errors above.
    call npm run restore
    pause
    exit /b 1
)

:: Verify Final Signature
echo.
echo [INFO] Verifying installer signature...
set "INSTALLER_PATH=dist\Windows-Runtime-Host-Setup-!VERSION!.exe"
if exist "!INSTALLER_PATH!" (
    if not "!SIGNTOOL_PATH!"=="" (
        signtool verify /pa /v "!INSTALLER_PATH!"
        if !errorlevel! neq 0 (
            echo [WARNING] Signature verification failed for !INSTALLER_PATH!
        ) else (
            echo [SUCCESS] Signature verified for !INSTALLER_PATH!
        )
    )
)

:: Restore
echo [INFO] Restoring clean code...
call npm run restore
cd ..

echo.
echo ==========================================
echo [SUCCESS] ALL BUILDS COMPLETE AND UPLOADED!
echo ==========================================
echo.
echo [IMPORTANT] Self-Signed Certificates:
echo Your installer IS signed, but because it is a "Self-Signed" certificate:
echo 1. Windows will still show a warning until you "Trust" the certificate locally.
echo 2. To avoid the warning, you must right-click the .exe -^> Properties -^> Digital Signatures 
echo    -^> Details -^> View Certificate -^> Install Certificate (Local Machine) 
echo    -^> Place in "Trusted Root Certification Authorities".
echo.
pause
