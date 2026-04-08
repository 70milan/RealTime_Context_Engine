# WinHostSvc.py - Backend launcher for Interview Assistant
# Electron spawns this EXE directly as a child process (NOT via Windows SCM).
# We simply start uvicorn and serve the FastAPI app on port 5050.

import sys
import os
import uvicorn

# Ensure the directory containing main.py is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Unicode output encoding for Windows (prevents charmap errors in piped output)
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, Exception):
        pass

print("[WinHostSvc] Importing backend app...")

from main import app

if __name__ == '__main__':
    print("[WinHostSvc] Starting uvicorn on http://0.0.0.0:5050")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5050,
        log_level="info",
        use_colors=False
    )
