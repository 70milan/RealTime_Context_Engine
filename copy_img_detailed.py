import os
import shutil
from PIL import Image

src = r"C:\Users\milan\.gemini\antigravity\brain\9f6acc06-3f2c-4b51-ad63-c4ed0dbc02d7\detailed_architecture_diagram_1772856734124.png"
dst1 = r"C:\Data Engineering\release_package\detailed_architecture.png"
dst2 = r"C:\Data Engineering\release_package\detailed_architecture.jpg"

print(f"SRC EXISTS: {os.path.exists(src)}")
if os.path.exists(src):
    shutil.copy2(src, dst1)
    print(f"COPIED TO: {dst1}")
    
    img = Image.open(src).convert('RGB')
    img.save(dst2, "JPEG", quality=100)
    print(f"CONVERTED TO: {dst2}")
