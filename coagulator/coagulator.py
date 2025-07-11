# The original source code for this program is in ../old/coagulator.py. I wrote it using what turned out to be a noncompliant and incomplete web_socket_server framework, so I asked ChatGPT to rewrite it using the python websockets framework and then modified the result to make it work. In the end, Chat GPT is responsible for the asyncio stuff mostly, though even some of that has changed since.

import asyncio
import argparse
import configobj
import json
import mimetypes
import os
import random
import re
import sys
import time
import traceback
import urllib.parse
import websockets
import websockets.asyncio.server

def g(): pass #globals
g.provider_rev = 4
g.user_rev = 4
g.next_client_id = 1
g.next_web_id = 10000000

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
				result["rate"] = value
			elif key == "p":
				result["pitch"] = value
		except ValueError:
			continue
	return result

def find_provider_for_voice(voice):
	"""Searches the list of voices for a provider to send a speech request to given a voice name."""
	if not voice:
		return voice, None
	voice = voice.strip()
	user = None
	if "/" in voice: user, delim, voice = voice.partition("/")
	voice = voice.lower()
	instance = 1
	if voice[0].isdigit() and "." in voice:
		instance, delim, voice = voice.partition(".")
		instance = int(instance)
	found = 1
	for v in sorted(g.voices, key=len):
		choices = list(g.voices[v])
		for c in list(choices):
			if user and getattr(g.clients[c]["ws"], "username") != user: choices.remove(c)
		if len(choices) < 1: continue
		if re.search(r"\b" + voice + r"\b", v.lower()):
			if instance == found:
				return v, random.choice(choices)
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
		g.speech_requests[meta["id"]] = (client, provider)

async def on_message(ws, client, message):
	"""Handles incoming WebSocket messages."""
	if isinstance(message, bytes):
		meta_len = int.from_bytes(message[:2], "little")
		meta = message[2:meta_len+2].decode()
		if meta.startswith("{"): meta = json.loads(meta)
		else: meta = {"id": meta}
		if meta["id"] in g.speech_requests: 
			await g.speech_requests[meta["id"]][0]["ws"].send(message)
			del g.speech_requests[meta["id"]]
		return
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
	elif "provider" in msg and "status" in msg and "id" in msg and msg["id"] in g.speech_requests:
		await g.speech_requests[msg["id"]][0]["ws"].send(message)
		if "abort" in msg and msg["abort"]: del g.speech_requests[msg["id"]]
	elif "user" in msg:
		if msg["user"] < g.user_rev:
			await ws.send(json.dumps({"error": f"must be revision {g.user_rev} or higher"}))
			return
		if "request" in msg:
			await handle_speech_request(client, msg["request"], str(msg.get("id", "")))
		elif "command" in msg:
			if msg["command"] == "abort":
				for req_id in list(g.speech_requests):
					req = g.speech_requests[req_id]
					if req[0]["ws"] == ws:
						await req[1].send(json.dumps({"abort": req_id}))
						del(g.speech_requests[req_id])
		else:
			await ws.send(json.dumps({"voices": list(g.voices)}))

async def notify_all_clients(data, ignore_list = []):
	"""Broadcasts a message to all connected clients."""
	if g.clients:
		await asyncio.gather(*[client["ws"].send(json.dumps(data)) for client in g.clients.values() if not client["id"] in ignore_list])

async def on_client_disconnect(ws, client_id):
	"""Handles client disconnections, updating voice providers and speech requests as needed."""
	try:
		lost_voice = False
		for v in list(g.voices):
			if client_id in g.voices[v]:
				while client_id in g.voices[v]: g.voices[v].remove(client_id)
				if len(g.voices[v]) < 1:
					del g.voices[v]
					lost_voice = True
		if lost_voice: await notify_all_clients({"voices": list(g.voices)}, [client_id])
		for r in list(g.speech_requests):
			if g.speech_requests[r][1] == ws:
				await g.speech_requests[r][0]["ws"].send(json.dumps({"warning": f"provider servicing request {r} disappeared", "request_id": r}))
			if g.speech_requests[r][0]["ws"] == ws or g.speech_requests[r][1] == ws:
				del g.speech_requests[r]
	except websockets.exceptions.ConnectionClosedOK: pass

class web_send:
	"""Helper class for STAR's tiny frontend API that allows it to be able to work with existing infrastructure."""
	def __init__(self, connection): self.connection = connection
	async def __call__(self, message):
		"""So that the little HTTP API can be added without altering most of the coagulator's code, we just monkeypatch the connection.send method in the below connection_request_handler function so that the existing infrastructure just continues to work. This is the patched send function."""
		if isinstance(message, str):
			self.connection.response_mime = "application/json"
			self.connection.response_extension = ""
			self.connection.response = message
		elif isinstance(message, bytes):
			meta_len = int.from_bytes(message[:2], "little")
			meta = message[2:meta_len+2].decode()
			if meta.startswith("{"): meta = json.loads(meta)
			else: meta = {"id": meta}
			self.connection.response_extension = meta.get("extension", "wav")
			self.connection.response_mime = mimetypes.guess_type(f"synthesized.{self.connection.response_extension}")[0]
			self.connection.response = audio = message[meta_len + 2:]
def make_http_response(connection, status, mime, body):
	"""The websockets API for http headers is a bit bulky, we need a helper function to set up a response that may be either text or binary."""
	if isinstance(body, str): body = body.encode()
	r = connection.respond(status, "")
	del(r.headers["Content-Type"])
	del(r.headers["Content-Length"])
	r.headers.update({"Content-Length": len(body), "Content-Type": mime})
	r.body = body
	return r
async def connection_request_handler(connection, request):
	"""Called by the websockets framework upon each http connection, this checks for basic authentication before handling and serving up the coagulator's simple HTTP frontend if needed."""
	auth_failure = await g.authorize(connection, request) if not g.authless else None
	if auth_failure: return auth_failure
	if "upgrade" in request.headers: return # This is a websocket connection
	#Otherwise, a very simple http API/web frontend is available,
	if "http_frontend" in g.config and not g.config.as_bool("http_frontend"): return # unless it's been disabled.
	path, delim, query = request.path.partition("?")
	if path == "/":
		with open(os.path.join(os.path.dirname(__file__), "coagulator_index.html"), "r") as f: webpage = f.read().replace("{{username}}", getattr(connection, "username", "visitor")).replace("{{voicecount}}", str(len(g.voices)))
		return make_http_response(connection, 200, "text/html", webpage)
	elif path == "/voices": return make_http_response(connection, 200, "application/json", json.dumps({"voices": list(g.voices)}))
	elif path == "/synthesize":
		args = urllib.parse.parse_qs(query.partition("#")[0])
		if not args or not "voice" in args and not "text" in args: return connection.respond(400, "missing voice or text argument")
		connection.send = web_send(connection)
		connection.response = b""
		voice = args["voice"][0].partition(":")[0] if "voice" in args and args["voice"] else ""
		params = []
		for arg in args:
			if arg in ["voice", "text"]: continue
			params += f"{arg}={args[arg]}"
		if voice:
			if params: voice += "<" + (" ".join(params)) + ">"
			voice += ": "
			g.next_web_id += 1
		await handle_speech_request({"ws": connection, "id": g.next_web_id}, f"{voice}{args['text'][0]}")
		while not connection.response:
			await asyncio.sleep(0.1)
		if isinstance(connection.response, str): return make_http_response(connection, 400, connection.response_mime, connection.response)
		r = make_http_response(connection, 200, connection.response_mime, connection.response)
		r.headers["content-disposition"] = f'inline; filename="speech{int(time.time())}.{connection.response_extension}"'
		return r
	else: return connection.respond(404, "not found")

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
		del(g.clients[client_id])
		await on_client_disconnect(ws, client_id)

def handle_args():
	"""Uses argparse to process and apply command line arguments."""
	p = argparse.ArgumentParser(argument_default = argparse.SUPPRESS)
	p.add_argument("--authless", action = "store_true")
	p.add_argument("--config", nargs = "?", const = "coagulator.ini")
	p.add_argument("--host", nargs = "?", const = "0.0.0.0")
	p.add_argument("--port", nargs = "?", type=int, const = 7774)
	p.add_argument("--configure", action = "store_true")
	g.args_parsed = p.parse_args(sys.argv[1:])
	g.authless = "authless" in g.args_parsed and g.args_parsed.authless
	g.do_configuration_interface = "configure" in g.args_parsed
	if "config" in g.args_parsed: g.config_filename = g.args_parsed.config
	else: g.config_filename = "coagulator.ini"
	g.config = configobj.ConfigObj(g.config_filename)
	if "host" in g.args_parsed: g.config["bind_address"] = g.args_parsed.host
	if "port" in g.args_parsed:
		if g.args_parsed.port < 1 or g.args_parsed.port > 65535: sys.exit("bind port must be between 1 and 65535")
		g.config["bind_port"] = g.args_parsed.port


def configuration():
	"""Command line based configuration interface that allows modifying users, as well as changing the bind host/port and other properties."""
	if not "users" in g.config: g.config["users"] = {}
	def useradd(username = ""):
		"""Also handles updating the password for an existing user."""
		while True:
			if not username: username = input("enter a username or leave blank to go back").strip()
			if not username: return
			if len(username) > 64:
				print("exceeded recommended username length of less than 64 characters")
				continue
			pwd = input(" enter password or leave blank to go back").strip()
			if not pwd: return
			if not username in g.config["users"]: g.config["users"][username] = {}
			g.config["users"][username]["password"] = pwd
			break
		print("configuration updated")
	def usermod(username):
		while username in g.config["users"]:
			opt = input(f"options for {username}:\n1: change password\n2: delete user\nleave blank to go back")
			if not opt: return
			if not opt.isdigit():
				print("only numbers accepted")
				continue
			opt = int(opt)
			if opt == 1: useradd(username)
			elif opt == 2: userdel(username)
	def userdel(username):
		confirm = input(f"Are you sure you want to delete the user {username}? Input y for yes or anything else to cancel.")
		if confirm != "y": return
		del(g.config["users"][username])
		print("configuration updated")
	def userlist():
		while True:
			if not "users" in g.config or len(g.config["users"]) < 1:
				print("no users")
				return
			if len(g.config["users"]) != 1: print(f"There are {len(g.config['users'])} users, select one by it's number or leave blank to go back")
			else: print("There is 1 user, select it by it's number or leave blank to go back")
			for i, u in enumerate(g.config["users"]):
				print(f"{i + 1}: {u}")
			opt = input()
			if not opt: return
			if not opt.isdigit() or int(opt) < 1 or int(opt) > len(g.config["users"]):
				print("must be a valid user number")
				continue
			usermod(list(g.config["users"])[int(opt) -1])
	def toggle_http_frontend():
		value = g.config.as_bool("http_frontend") if "http_frontend" in g.config else True
		g.config["http_frontend"] = not value
		print("HTTP frontend " + ("enabled" if not value else "disabled"))
	def set_var(varname, prompt, default = "", validator = None):
		data = g.config.get(varname, default)
		while True:
			new_data = input(f"{prompt} (currently {data}), leave blank to go back without modifying value")
			if not new_data: return
			validate_fail = validator(new_data) if validator else ""
			if validate_fail:
				print(validate_fail)
				continue
			g.config[varname] = new_data
			break
		print("configuration updated")
	options = [("add a user", "useradd"), ("change or delete a user", "usermod"), ("set bind address", "bindaddr"), ("set bind port", "bindport"), ("{frontend_action} HTTP frontend", "http_frontend"), ("save and exit", "X"), ("exit without saving", "x")]
	options_str = "Select an option, follow all input with return:\n"
	for i, o in enumerate(options):
		options_str += f"{i + 1}: {o[0]}\n"
	while True:
		try: opt = input(options_str.format(frontend_action = "enable" if "http_frontend" in g.config and not g.config.as_bool("http_frontend") else "disable"))
		except EOFError: return
		if not opt: continue
		if not opt.isdigit():
			print("only digits accepted")
			continue
		opt = int(opt)
		if opt < 1 or opt > len(options):
			print(f"option {opt} out of range")
			continue
		opt = options[opt -1][1]
		if opt == "useradd": useradd()
		elif opt == "usermod": userlist()
		elif opt == "bindaddr": set_var("bind_address", "enter address to bind to", "0.0.0.0")
		elif opt == "bindport": set_var("bind_port", "enter port to bind to", 7774, lambda value: "port must be a number between 1 and 65535" if not value.isdigit() or int(value) < 1 or int(value) > 65535 else "")
		elif opt == "http_frontend": toggle_http_frontend()
		elif opt == "X":
			g.config.write()
			print("configuration saved")
			return
		elif opt == "x": return

async def main():
	g.speech_requests = {}
	g.voices = {}
	g.clients = {}
	handle_args()
	if g.do_configuration_interface: return configuration()
	g.authorize = websockets.asyncio.server.basic_auth(check_credentials = lambda username, password: "users" in g.config and username in g.config["users"] and g.config["users"][username].get("password", "") == password)
	async with websockets.asyncio.server.serve(client_handler, g.config.get("bind_address", "0.0.0.0"), int(g.config.get("bind_port", 7774)), max_size = int(g.config.get("max_packet_size", 1024 * 1024 * 10)), max_queue = 4096,  process_request = connection_request_handler):
		print("Coagulator up.")
		await asyncio.get_running_loop().create_future()

if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print("coagulator down.")
