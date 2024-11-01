# This code was almost entirely generated by chatGPT with minor modifications to make it work the way we need.

import json
import base64
import asyncio
import os
import sys
import tempfile
import websockets
import pyttsx3
from configobj import ConfigObj

# Load configuration
config = ConfigObj("pyttsx.ini")
websocket_url = config.get("url", "ws://localhost:7774")

# Initialize text-to-speech engine
engine = pyttsx3.init()
voices = []
for v in engine.getProperty("voices"):
	voice = v.name.replace("_", " ").replace("-", " ").replace("(", " ").replace(")", " ").replace("   ", " ").replace("  ", " ").strip()
	if "aliases" in config and voice in config["aliases"]: voice = config["aliases"][voice]
	if not voice: continue
	voices.append((voice, v.id))

# Define function to save synthesized speech to a wave file
def synthesize_to_wave(event):
	global engine
	for v in voices:
		if v[0] != event["voice"]: continue
		event["voice"] = v[1]
		break
	engine.setProperty("voice", event["voice"])
	old_rate = engine.getProperty("rate") if "rate" in event else None
	old_pitch = engine.getProperty("pitch") if "pitch" in "event" else None
	#if "rate" in event: engine.setProperty("rate", int(event["rate"]))
	#if "pitch" in event: engine.setProperty("pitch", float(event["pitch"]))
	with tempfile.NamedTemporaryFile(delete=False) as fp:
		fp.close()
	engine.save_to_file(event["text"], fp.name)
	wave_data = None
	try:
		engine.runAndWait()
		#if "rate" in event: engine.setProperty("rate", old_rate)
		#if "pitch" in event: engine.setProperty("pitch", old_pitch)
		if sys.platform == "darwin":
			# frustratingly pyttsx3 on MacOS produces aif files right now.
			os.rename(fp.name, "tmp.aiff")
			fp.name = fp.name + ".wav"
			os.system(f"ffmpeg -y -i tmp.aiff \"{fp.name}\" 2>/dev/null")
			os.remove("tmp.aiff")
		# Read the wave file and encode it to base64
		with open(fp.name, "rb") as wave_file:
			wave_data = wave_file.read()
		os.unlink(fp.name)
	except Exception as e:
		print(e)
		engine.stop()
		engine = pyttsx3.init()
		return b""
	return wave_data

# WebSocket handling
async def send_voices(websocket):
	data = {
		"provider": 2,
		"voices": [v[0] for v in voices]
	}
	await websocket.send(json.dumps(data))

async def handle_websocket():
	should_exit = False
	while not should_exit:
		try:
			async with websockets.connect(websocket_url, max_size = None, max_queue = 4096) as websocket:
				print(f"connected {len(voices)} voices")
				await send_voices(websocket)
				while True:
					message = await websocket.recv()
					try:
						event = json.loads(message)
						if "voice" in event and "text" in event:
							encoded_wave = synthesize_to_wave(event)
							response = len(event["id"]).to_bytes(2, "little") + event["id"].encode() + encoded_wave
							await websocket.send(response)
					except json.JSONDecodeError:
						print("Received an invalid JSON message:", message)
		except (websockets.exceptions.WebSocketException, websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK, ConnectionRefusedError, TimeoutError) as e:
					print(f"reconnecting... {e}")
		except KeyboardInterrupt: return

# Main entry point
if __name__ == "__main__":
	try:
		asyncio.run(handle_websocket())
	except KeyboardInterrupt: pass
