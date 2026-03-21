import sys
import os
from pathlib import Path

# Simulate frozen environment
sys.frozen = True
sys.executable = r"C:\Data Engineering\release_package\backend\interview-backend.exe"

# Logic from backend/main.py
if getattr(sys, 'frozen', False):
    app_data = os.getenv('APPDATA')
    if app_data:
        BASE_DIR = Path(app_data) / "jobandit" / "backend"
    else:
        BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

print(f"\n[VERIFICATION] IF this were the installed app, data would be stored in:\n{BASE_DIR}")
print(f"\nDoes this directory exist? {BASE_DIR.exists()}")
