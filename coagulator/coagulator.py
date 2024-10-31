import json
import random
import re
import time
from websocket_server import WebsocketServer

def g(): pass #globals
g.provider_rev = 1
g.user_rev = 1

def parse_speech_meta(meta):
	"""Takes speech metadata such as "Sam" or "Sam<r=4 p=-2>" and returns a dictionary of parsed properties such as voice, rate and pitch."""
	if meta.find("<") < 0: return {"voice": meta}
	voice, part, params = meta.partition("<")
	result = {"voice": voice}
	params = params[:-1]
	params = params.split(" ")
	for p in params:
		try:
			p = p.strip().split("=")
			if len("p") < 2: continue
			if p[0] == "r": result["rate"] = float(p[1])
			elif p[0] == "p": result["pitch"] = float(p[1])
		except ValueError: continue

def find_provider_for_voice(voice):
	"""Searches the list of voices for a provider to send a speech request to given a voice name."""
	for v in g.voices:
		if re.search(r"\b" + voice + r"\b", v): return (v, random.choice(g.voices[v]))
	return (voice, None)

def handle_speech_request(client, server, request, id = ""):
	"""Receives a list of requests such as ["Sam: hello", "Alex<p=4>: What's up!"] and dispatches each line to a voice provider for synthesis."""
	if not "speech_sequence" in client or id: client["speech_sequence"] = 0
	if id: id = "_" + id
	if type(request) == str: request = [request]
	for line in request:
		raw_meta, part, text = line.partition(": ")
		if not text.strip():
			server.send_message(client, json.dumps({"warning": f"no text found in line {line}"}))
			continue
		meta = parse_speech_meta(raw_meta)
		if not "voice" in meta:
			server.send_message(client, json.dumps({"warning": f"failed to parse voice meta {raw_meta}"}))
			continue
		meta["voice"], provider = find_provider_for_voice(meta["voice"])
		if not provider:
			server.send_message(client, json.dumps({"warning": f"failed to find provider for {meta['voice']}"}))
			continue
		client["speech_sequence"] += 1
		meta["text"] = text
		meta["id"] = f"{client['id']}{id}_{client['speech_sequence']}"
		server.send_message(provider, json.dumps(meta))
		g.speech_requests[meta["id"]] = client

def on_message(client, server, message):
	"""This callback is fired every time we receive a new message on our server websocket. We handle both provider and user messages here."""
	msg = {}
	try:
		msg = json.loads(message)
	except: return
	if "provider" in msg and "voices" in msg:
		if msg["provider"] < g.provider_rev:
			server.send_message(client, json.dumps({"error", f"must be revision {g.provider_rev} or higher"}))
			return
		for v in msg["voices"]:
			if v in g.voices: g.voices[v].append(client)
			else: g.voices[v] = [client]
	elif "user" in msg:
		if msg["user"] < g.user_rev:
			server.send_message(client, json.dumps({"error", f"must be revision {g.user_rev} or higher"}))
			return
		if "request" in msg: handle_speech_request(client, server, msg["request"], str(msg["id"]) if "id" in msg else "")
		else: server.send_message(client, json.dumps({"voices": list(g.voices)}))
	elif "speech" in msg and msg["speech"] in g.speech_requests and "data" in msg:
		server.send_message(g.speech_requests[msg["speech"]], message)
		del(g.speech_requests[msg["speech"]])

def on_lost_client(client, server):
	"""If a provider disconnects, we must remove it's list of voices. If a user disconnects mid-synthesis, we must remove it's speech requests."""
	for v in list(g.voices):
		if client in g.voices[v]:
			g.voices[v].remove(client)
			if len(g.voices[v]) == 0: del(g.voices[v])
	for r in list(g.speech_requests):
		if g.speech_requests[r] == client: del(g.speech_requests[r])

def main():
	g.speech_requests = {}
	g.voices = {}
	g.ws = WebsocketServer(port = 7774, host = "0.0.0.0")
	g.ws.set_fn_client_left(on_lost_client)
	g.ws.set_fn_message_received(on_message)
	g.ws.run_forever()
	try:
		while 1: time.sleep(5)
	except KeyboardInterrupt:
		print("shutting down")
		g.ws.shutdown_gracefully()

if __name__ == "__main__":
	main()
