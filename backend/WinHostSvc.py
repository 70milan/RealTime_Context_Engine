# WinHostSvc.py - Backend launcher for Interview Assistant
# Electron spawns this EXE directly as a child process (NOT via Windows SCM).
# We simply start uvicorn and serve the FastAPI app on port 5050.

import multiprocessing

# MUST run before anything else. In a frozen (PyInstaller) exe, any library that
# uses multiprocessing (e.g. py-cpuinfo) re-launches this same EXE with
# "--multiprocessing-fork". Without freeze_support() that child re-runs the whole
# backend, which spawns another child, and so on — a runaway process chain that
# eats CPU/RAM and keeps the real server from ever binding port 5050.
multiprocessing.freeze_support()

import sys
import os
import uvicorn

# Ensure the directory containing main.py is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Unicode output encoding for Windows (prevents charmap errors in piped output).
# line_buffering so each log line reaches Electron immediately instead of sitting
# in a block buffer that is lost when the process is force-killed.
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except (AttributeError, Exception):
        pass

def watch_parent():
    """Exit when the Electron process that launched us dies (crash, kill, Task
    Manager). Otherwise the orphaned backend keeps port 5050 and the next launch
    fails. Electron passes its PID in WINHOST_PARENT_PID; we block on its handle."""
    pid = os.getenv("WINHOST_PARENT_PID")
    if not pid or sys.platform != 'win32':
        return
    import ctypes
    import threading

    SYNCHRONIZE = 0x00100000
    INFINITE = 0xFFFFFFFF
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        print(f"[WinHostSvc] Parent {pid} not found - exiting")
        os._exit(0)

    def wait():
        kernel32.WaitForSingleObject(handle, INFINITE)
        print("[WinHostSvc] Parent process exited - shutting down backend")
        os._exit(0)

    threading.Thread(target=wait, daemon=True, name="parent-watchdog").start()

print("[WinHostSvc] Importing backend app...")

from main import app

if __name__ == '__main__':
    watch_parent()
    print("[WinHostSvc] Starting uvicorn on http://127.0.0.1:5050")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=5050,
        log_level="info",
        use_colors=False
    )
