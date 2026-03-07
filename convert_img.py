from PIL import Image
img = Image.open(r"C:\Users\milan\.gemini\antigravity\brain\9f6acc06-3f2c-4b51-ad63-c4ed0dbc02d7\architecture_diagram_1772856157817.png")
rgb_im = img.convert('RGB')
rgb_im.save(r"C:\Data Engineering\release_package\architecture.jpg", "JPEG", quality=100)
print("conversion complete")
