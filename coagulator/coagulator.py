# The original source code for this program is in ../old/coagulator.py. I wrote it using what turned out to be a noncompliant and incomplete web_socket_server framework, so I asked ChatGPT to rewrite it using the python websockets framework and then modified the result to make it work. In the end, Chat GPT is responsible for the asyncio stuff mostly, though even some of that has changed since.

import asyncio
import argparse
import configobj
import json
import random
import re
import sys
import time
import traceback
import websockets
import websockets.asyncio.server

def g(): pass #globals
g.provider_rev = 3
g.user_rev = 3
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
		g.speech_requests[meta["id"]] = (client, provider)

async def on_message(ws, client, message):
	"""Handles incoming WebSocket messages."""
	if type(message) == bytes:
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
				for req_id, req in enumerate(g.speech_requests):
					if req[0] == websocket: await req[1].send(json.dumps({"abort": req_id}))
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
				g.voices[v].remove(client_id)
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
	options = [("add a user", "useradd"), ("change or delete a user", "usermod"), ("set bind address", "bindaddr"), ("set bind port", "bindport"), ("save and exit", "X"), ("exit without saving", "x")]
	options_str = "Select an option, follow all input with return:\n"
	for i, o in enumerate(options):
		options_str += f"{i + 1}: {o[0]}\n"
	while True:
		opt = input(options_str)
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
	async with websockets.asyncio.server.serve(client_handler, g.config.get("bind_address", "0.0.0.0"), int(g.config.get("bind_port", 7774)), max_size = int(g.config.get("max_packet_size", 1024 * 1024 * 5)), max_queue = 4096, process_request = websockets.asyncio.server.basic_auth(check_credentials = lambda username, password: "users" in g.config and username in g.config["users"] and g.config["users"][username].get("password", "") == password) if not g.authless else None):
		print("Coagulator up.")
		await asyncio.get_running_loop().create_future()

if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print("coagulator down.")
