# The original source code for this program is in coagulator_old.py. I wrote it using what turned out to be a noncompliant and incomplete web_socket_server framework, so I asked ChatGPT to rewrite it using the python websockets framework and then modified the result to make it work.

import json
import random
import re
import time
import asyncio
import traceback
import websockets
import websockets.asyncio.server

def g(): pass #globals
g.provider_rev = 1
g.user_rev = 1
g.next_client_id = 1

def parse_speech_meta(meta):
	"""Takes speech metadata such as "Sam" or "Sam<r=4 p=-2>" and returns a dictionary of parsed properties such as voice, rate, and pitch."""
	if "<" not in meta:
		return {"voice": meta}
	voice, _, params = meta.partition("<")
	result = {"voice": voice}
	params = params.rstrip(">")
	for p in params.split(" "):
		try:
			key, value = p.strip().split("=")
			if key == "r":
				result["rate"] = float(value)
			elif key == "p":
				result["pitch"] = float(value)
		except ValueError:
			continue
	return result

def find_provider_for_voice(voice):
	"""Searches the list of voices for a provider to send a speech request to given a voice name."""
	if not voice:
		return voice, None
	voice = voice.lower().strip()
	instance = 1
	if voice[0].isdigit() and "." in voice:
		instance, voice = int(voice.split(".")[0]), voice.split(".")[1]
	found = 1
	for v in sorted(g.voices, key=len):
		if re.search(r"\b" + voice + r"\b", v.lower()):
			if instance == found:
				return v, random.choice(g.voices[v])
			else:
				found += 1
	return voice, None

async def handle_speech_request(client, request, id=""):
	"""Processes and dispatches each speech request line to the appropriate voice provider."""
	if "speech_sequence" not in client or id:
		client["speech_sequence"] = 0
	if id:
		id = "_" + id
	if isinstance(request, str):
		request = [request]
	for line in request:
		raw_meta, _, text = line.partition(": ")
		if not text.strip():
			await client["ws"].send(json.dumps({"warning": f"no text found in line {line}"}))
			continue
		meta = parse_speech_meta(raw_meta)
		if "voice" not in meta:
			await client["ws"].send(json.dumps({"warning": f"failed to parse voice meta {raw_meta}"}))
			continue
		meta["voice"], provider = find_provider_for_voice(meta["voice"])
		if not provider:
			await client["ws"].send(json.dumps({"warning": f"failed to find provider for {meta['voice']}"}))
			continue
		provider = g.clients[provider]["ws"]
		client["speech_sequence"] += 1
		meta.update({"text": text, "id": f"{client['id']}{id}_{client['speech_sequence']}"})
		await provider.send(json.dumps(meta))
		g.speech_requests[meta["id"]] = client

async def on_message(ws, client, message):
	"""Handles incoming WebSocket messages."""
	try:
		msg = json.loads(message)
	except json.JSONDecodeError:
		return
	if "provider" in msg and "voices" in msg:
		if msg["provider"] < g.provider_rev:
			await ws.send(json.dumps({"error": f"must be revision {g.provider_rev} or higher"}))
			return
		gained_voice = False
		for v in msg["voices"]:
			if v in g.voices:
				g.voices[v].append(client["id"])
			else:
				g.voices[v] = [client["id"]]
				gained_voice = True
		if gained_voice:
			await notify_all_clients({"voices": list(g.voices)}, [client["id"]])
	elif "user" in msg:
		if msg["user"] < g.user_rev:
			await ws.send(json.dumps({"error": f"must be revision {g.user_rev} or higher"}))
			return
		if "request" in msg:
			await handle_speech_request(client, msg["request"], str(msg.get("id", "")))
		else:
			await ws.send(json.dumps({"voices": list(g.voices)}))
	elif "speech" in msg and msg["speech"] in g.speech_requests and "data" in msg:
		await g.speech_requests[msg["speech"]]["ws"].send(message)
		del g.speech_requests[msg["speech"]]

async def notify_all_clients(data, ignore_list = []):
	"""Broadcasts a message to all connected clients."""
	if g.clients:
		await asyncio.gather(*[client["ws"].send(json.dumps(data)) for client in g.clients.values() if not client["id"] in ignore_list])

async def on_client_disconnect(ws, client_id):
	"""Handles client disconnections, updating voice providers and speech requests as needed."""
	lost_voice = False
	for v in list(g.voices):
		if client_id in g.voices[v]:
			g.voices[v].remove(client_id)
			if len(g.voices[v]) < 1:
				del g.voices[v]
				lost_voice = True
	if lost_voice: await notify_all_clients({"voices": list(g.voices)}, [client_id])
	for r in list(g.speech_requests):
		if g.speech_requests[r]["ws"] == ws:
			del g.speech_requests[r]

async def client_handler(ws):
	"""Manages WebSocket client connections."""
	client_id = g.next_client_id
	g.next_client_id += 1
	client = {"ws": ws, "id": client_id}
	g.clients[client_id] = client
	try:
		async for message in ws:
			await on_message(ws, client, message)
	except websockets.ConnectionClosed:
		pass
	except (asyncio.exceptions.CancelledError, KeyboardInterrupt):
		print("shutting down...")
		return
	except websockets.exceptions.ConnectionClosedOK: pass
	except: traceback.print_exc()
	finally:
		del g.clients[client_id]
		await on_client_disconnect(ws, client_id)

async def main():
	g.speech_requests = {}
	g.voices = {}
	g.clients = {}
	async with websockets.asyncio.server.serve(client_handler, "0.0.0.0", 7774, max_size = 1024 * 1024 * 5, max_queue = 4096):
		print("Coagulator up.")
		await asyncio.get_running_loop().create_future()

if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print("coagulator down.")
