import asyncio
import websockets
import json
import traceback

async def test():
    uri = "ws://127.0.0.1:5050/realtime"
    try:
        async with websockets.connect(uri) as ws:
            print("Connected to backend!")
            
            # Start a background task to receive messages
            async def receive():
                while True:
                    try:
                        msg = await ws.recv()
                        print(f"Received: {msg}")
                    except websockets.exceptions.ConnectionClosed:
                        print("Connection closed")
                        break
                    except Exception as e:
                        print(f"Receive error: {e}")
                        break
            
            asyncio.create_task(receive())
            
            # Construct a base64 encoded audio fragment of silence
            # 24kHz * 1sec = 24000 samples = 48000 bytes. We send a bit less.
            import base64
            silence = bytearray(48000)
            b64_silence = base64.b64encode(silence).decode('utf-8')
            
            print("Sending audio data...")
            await ws.send(b64_silence)
            
            # Wait for 5 seconds to see any responses
            await asyncio.sleep(5)
            
    except Exception as e:
        print("Error:", traceback.format_exc())

asyncio.run(test())
