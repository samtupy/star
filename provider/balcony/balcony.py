import json
import base64
import asyncio
import os
import subprocess
import sys
import traceback
import websockets

from configobj import ConfigObj

# Load configuration
config = ConfigObj("balcony.ini")
websocket_url = config.get("url", "ws://localhost:7774")

raw = subprocess.run(["balcon", "-l"], shell = True, capture_output = True, text = True).stdout.split("\n")
voices = []
for v in raw:
	if not v or not v.startswith(" "): continue
	voice = v
	if "::" in voice: voice = voice[voice.find("::") + 3:]
	voices.append((voice.replace("_", " ").replace("-", " ").replace("(", " ").replace(")", " ").replace(":", " ").replace("   ", " ").replace("  ", " ").strip(), v.strip()))

def synthesize_to_wave(event):
	for v in voices:
		if v[0] != event["voice"]: continue
		event["voice"] = v[1]
		break
	try:
		extra_args = ["-n", event["voice"], "-t", event["text"], "-w", "tmp.wav"]
		if "rate" in event: extra_args += ["-s", str(int(event["rate"]))]
		if "pitch" in event: extra_args += ["-p", str(int(event["pitch"]))]
		subprocess.run(["balcon"] + extra_args, shell = True)
		wave_data = None
		with open("tmp.wav", "rb") as f:
			wave_data = base64.b64encode(f.read()).decode("UTF8")
		os.unlink("tmp.wav");
	except Exception as e:
		print(e)
		return ""


# WebSocket handling
async def send_voices(websocket):
	data = {
		"provider": 1,
		"voices": [v[0] for v in voices]
	}
	await websocket.send(json.dumps(data))

async def handle_websocket():
	should_exit = False
	while not should_exit:
		try:
			async with websockets.connect(websocket_url, max_size = None) as websocket:
				await send_voices(websocket)
				while True:
					message = await websocket.recv()
					try:
						event = json.loads(message)
						if "voice" in event and "text" in event:
							encoded_wave = synthesize_to_wave(event)
							response = {
								"speech": event["id"],
								"data": encoded_wave
							}
							await websocket.send(json.dumps(response))
					except json.JSONDecodeError:
						print("Received an invalid JSON message:", message)
		except (websockets.exceptions.WebSocketException, websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK, ConnectionRefusedError, TimeoutError) as e:
			traceback.print_exc()
			print(f"reconnecting... {e}")

# Main entry point
if __name__ == "__main__":
	asyncio.run(handle_websocket())
