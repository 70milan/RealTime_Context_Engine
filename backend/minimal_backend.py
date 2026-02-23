
from fastapi import FastAPI
import uvicorn
import sys

print("[MINIMAL] Starting...")
app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

if __name__ == "__main__":
    print("[MINIMAL] Running uvicorn...")
    try:
        uvicorn.run(app, host="127.0.0.1", port=5051)
    except Exception as e:
        print(f"[MINIMAL ERROR] {e}")
