import asyncio
import websockets
import json

async def test():
    uri = "ws://127.0.0.1:5050/realtime"
    try:
        async with websockets.connect(uri) as ws:
            print("Connected!")
            # Wait for any messages
            msg = await ws.recv()
            print("Received:", msg)
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
