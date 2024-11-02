import json
import asyncio
import os
import subprocess
import sys
import tempfile
import time
import traceback
import websockets.asyncio.client

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
	voice = voice.replace("_", " ").replace("-", " ").replace("(", " ").replace(")", " ").replace(":", " ").replace("   ", " ").replace("  ", " ").strip()
	if "aliases" in config and voice in config["aliases"]: voice = config["aliases"][voice]
	if not voice: continue
	voices.append((voice, v.strip()))

async def synthesize_to_wave(event):
	for v in voices:
		if v[0] == event["voice"]:
			event["voice"] = v[1]
			break
	try:
		with tempfile.NamedTemporaryFile(delete=False) as fp:
			fp.close()
		extra_args = ["-n", event["voice"], "-t", event["text"], "-w", fp.name]
		if "rate" in event: extra_args += ["-s", str(int(event["rate"]))]
		if "pitch" in event: extra_args += ["-p", str(int(event["pitch"]))]
		process = await asyncio.create_subprocess_exec("balcon", *extra_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags = subprocess.CREATE_NO_WINDOW)
		await process.communicate()
		wave_data = await asyncio.to_thread(read_wave_file, fp.name)
		os.unlink(fp.name)
		return wave_data
	except Exception as e:
		print(e)
		return b""

# Helper function to read binary file data
def read_wave_file(filename):
	with open(filename, "rb") as f:
		return f.read()

# WebSocket handling
async def send_voices(websocket):
	data = {
		"provider": 2,
		"voices": [v[0] for v in voices]
	}
	await websocket.send(json.dumps(data))

async def process_event(websocket, event):
	try:
		if "voice" in event and "text" in event:
			encoded_wave = await synthesize_to_wave(event)
			if not encoded_wave: return ""
			response = len(event["id"]).to_bytes(2, "little") + event["id"].encode() + encoded_wave
			await websocket.send(response)
	except Exception as e:
		print(f"Error processing event: {e}")
		traceback.print_exc()

async def handle_websocket():
	should_exit = False
	while not should_exit:
		try:
			async with websockets.asyncio.client.connect(websocket_url, max_size = None, max_queue = 4096) as websocket:
				await send_voices(websocket)
				print(f"Connected {len(voices)} voices.")
				while True:
					message = await websocket.recv()
					try:
						event = json.loads(message)
						asyncio.create_task(process_event(websocket, event))
					except json.JSONDecodeError:
						print("Received an invalid JSON message:", message)
		except KeyboardInterrupt:
			print("shutting down")
			should_exit = True
		except Exception as e:
			traceback.print_exc()
			print(f"reconnecting... {e}")
			time.sleep(3)

# Main entry point
if __name__ == "__main__":
	while True:
		try:
			asyncio.run(handle_websocket())
		except KeyboardInterrupt:
			print("shutting down")
			break
		except Exception as e:
			traceback.print_exc()
			print("reconnecting... {e}")
			time.sleep(10)
