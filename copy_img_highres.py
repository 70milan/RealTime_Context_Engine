import os
import shutil

src = r"C:\Users\milan\.gemini\antigravity\brain\9f6acc06-3f2c-4b51-ad63-c4ed0dbc02d7\architecture_high_resolution_1772857040986.png"
dst1 = r"C:\Data Engineering\release_package\architecture_simplified_clear_text.png"

print(f"SRC EXISTS: {os.path.exists(src)}")
if os.path.exists(src):
    shutil.copy2(src, dst1)
    print(f"COPIED TO: {dst1}")
