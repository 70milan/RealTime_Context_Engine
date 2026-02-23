@echo off
echo [CLEANUP] Terminating backend processes...
taskkill /F /IM WinHostSvc.exe /T 2>nul
taskkill /F /IM interview-backend.exe /T 2>nul
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM uvicorn.exe /T 2>nul
echo [CLEANUP] Checking port 5050...
netstat -ano | findstr :5050
echo [CLEANUP] Done.
