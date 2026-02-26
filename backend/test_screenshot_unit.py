import urllib.request
import json
import ssl
import base64

def test_screenshot():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Create a tiny 1x1 black pixel JPEG as base64
    # This is a valid base64 for a minimal JPEG
    minimal_jpeg_b64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUHCwgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDAREAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAf/aAAwDAQACEQMRAD8AUn7/2Q=="

    data = {
        "transcript": "What do you see in this image?",
        "role": "Software Engineer",
        "target_language": "Python",
        "screenshot": minimal_jpeg_b64,
        "save_to_context": False
    }

    req = urllib.request.Request(
        'http://127.0.0.1:5050/ai', 
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    print("Sending AI request with screenshot...")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            print("Status code:", response.getcode())
            res_data = json.loads(response.read().decode('utf-8'))
            print("AI Response:", res_data.get('answer', 'No answer key find'))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_screenshot()
