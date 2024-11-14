# This is the base provider class for STAR and implements as many common features as possible.

PROVIDER_REVISION = 3

import argparse
import asyncio
import configobj
import json
import os
import subprocess
import sys
import tempfile
import time
import toga
import traceback
import websockets.asyncio.client

class star_provider_configurator(toga.App):
	"""This is a small Toga app that allows one to configure the provider with a list of hosts to connect to, and any other future options."""
	def __init__(self, provider):
		self.provider = provider
		toga.App.__init__(self, "STAR provider configuration", "com.samtupy.StarProvider")
	def focus_settings(self):
		self.main_window.content = self.settings
		self.widgets["save_btn"].focus()
	def focus_mod_host(self):
		self.main_window.content = self.mod_host
		self.widgets["mod_host_input"].focus()
	def focus_mod_voice(self, voice_id):
		self.main_window.content = self.mod_voice
		self.widgets["mod_voice_alias_input"].value = self.provider.voices[voice_id]["alias"] if "alias" in self.provider.voices[voice_id] else ""
		self.widgets["mod_voice_enable"].value = self.provider.voices[voice_id]["enabled"]
		self.widgets["mod_voice_alias_label"].text = f"&Alias for {self.provider.voices[voice_id]['id']}"
		self.widgets["mod_voice_alias_input"].focus()
	def on_save_btn(self, button):
		c = configobj.ConfigObj(self.provider.config_filename)
		c["hosts"] = [i.url for i in self.hosts_list.data]
		for voice in self.voices_list.data:
			if not voice.enabled or hasattr(voice, "alias") and voice.alias:
				if not "voices" in c: c["voices"] = {}
				c["voices"][voice.id] = {"alias": voice.alias, "enabled": voice.enabled}
			elif "voices" in c and voice.id in c["voices"]: del(c["voices"][voice.id])
		c.write()
		self.request_exit()
	async def on_voice_edit_btn(self, button):
		sel = self.voices_list.selection
		if not sel: return await self.main_window.dialog(toga.InfoDialog("error", "no voice selected"))
		self.modding_voice = self.voices_list.data.index(sel)
		self.focus_mod_voice(sel.id)
	def on_hosts_new_btn(self, button):
		self.modding_host = -1
		self.focus_mod_host()
	async def on_hosts_edit_btn(self, button):
		sel = self.widgets["hosts_list"].selection
		if not sel: return await self.main_window.dialog(toga.InfoDialog("error", "no host selected"))
		self.modding_host = self.hosts_list.data.index(sel)
		self.mod_host_input.value = sel.url
		self.focus_mod_host()
	async def on_hosts_delete_btn(self, button):
		sel = self.widgets["hosts_list"].selection
		if not sel: return await self.main_window.dialog(toga.InfoDialog("error", "no host selected"))
		self.widgets["hosts_list"].data.remove(sel)
	async def on_mod_host_save(self, button):
		h = self.widgets["mod_host_input"].value
		self.widgets["mod_host_input"].value = ""
		if self.modding_host == -1: self.hosts_list.data.append((h))
		else: self.hosts_list.data[self.modding_host] = (h)
		self.focus_settings()
	async def on_mod_voice_save(self, button):
		self.voices_list.data[self.modding_voice].alias = self.widgets["mod_voice_alias_input"].value
		self.voices_list.data[self.modding_voice].enabled = self.widgets["mod_voice_enable"].value
		self.focus_settings()
	def on_setting_cancel(self, button):
		self.focus_settings()
	def startup(self):
		self.main_window = toga.MainWindow()
		self.settings = toga.Box()
		voices_label = toga.Label("&Voices");
		self.voices_list = toga.Table(headings = ["full name", "enabled", "alias"], data = [self.provider.voices[v] for v in self.provider.voices])
		voice_edit_btn = toga.Button("Edi&t voice...", on_press = self.on_voice_edit_btn);
		hosts_label = toga.Label("&Hosts", id = "hosts_label")
		self.hosts_list = toga.Table(id = "hosts_list", headings = ["URL"], data = [(i) for i in self.provider.hosts])
		hosts_new_btn = toga.Button("&New host...", on_press = self.on_hosts_new_btn);
		hosts_edit_btn = toga.Button("&Edit host...", on_press = self.on_hosts_edit_btn);
		hosts_delete_btn = toga.Button("&Delete host...", id = "hosts_delete_btn", on_press = self.on_hosts_delete_btn);
		save_btn = toga.Button("&Save", id = "save_btn", on_press = self.on_save_btn)
		self.settings.add(voices_label, self.voices_list, voice_edit_btn, hosts_label, self.hosts_list, hosts_new_btn, hosts_edit_btn, hosts_delete_btn, save_btn)
		self.settings = toga.ScrollContainer(content = self.settings)
		mod_host_label = toga.Label("&Host")
		self.mod_host_input = toga.TextInput(id = "mod_host_input", on_confirm = self.on_mod_host_save)
		mod_host_save = toga.Button("ok", on_press = self.on_mod_host_save)
		mod_host_cancel = toga.Button("Cancel", on_press = self.on_setting_cancel)
		self.mod_host = toga.Box(children = [mod_host_label, self.mod_host_input, mod_host_save, mod_host_cancel])
		mod_voice_alias_label = toga.Label("&Alias for voice", id = "mod_voice_alias_label")
		self.mod_voice_alias_input = toga.TextInput(id = "mod_voice_alias_input", on_confirm = self.on_mod_voice_save)
		mod_voice_enable = toga.Switch("&Enable voice", id = "mod_voice_enable")
		mod_voice_save = toga.Button("ok", on_press = self.on_mod_voice_save)
		mod_voice_cancel = toga.Button("Cancel", on_press = self.on_setting_cancel)
		self.mod_voice = toga.Box(children = [mod_voice_alias_label, self.mod_voice_alias_input, mod_voice_enable, mod_voice_save, mod_voice_cancel])
		self.main_window.show()
	def on_running(self):
		self.focus_settings()

class star_provider:
	"""A base class that can be used to implement any STAR provider able to be written in Python3. It abstracts all communication with coagulators, as much of the async stuff as possible, filtering voice names and more. This class should not be instantiated directly, but instead only it's children."""
	def __init__(self, provider_basename = os.path.splitext(sys.argv[0])[0], handle_argv = True, run_immedietly = True, synthesis_process = None, synthesis_process_rate = None, synthesis_process_pitch = None):
		"""The provider_basename argument should be set to a simple strings such as balcony or pyttsx. Set handle_argv to False if you don't wish for the default CLI interface. If you really wish to configure this object further than the constructor allows before running the provider, set run_immedietly to False. The default implementation makes it easy to implement executable based providers with  the synthesis_process arguments."""
		self.config_filename = f"{provider_basename}.ini"
		if synthesis_process: self.synthesis_process = synthesis_process
		if synthesis_process_rate: self.synthesis_process_rate = synthesis_process_rate
		if synthesis_process_pitch: self.synthesis_process_pitch = synthesis_process_pitch
		if handle_argv: self.handle_argv()
		self.config = configobj.ConfigObj(self.config_filename)
		if not hasattr(self, "hosts"): self.hosts = self.config.get("hosts", ["ws://localhost:7774"])
		if type(self.hosts) == str: self.hosts = [self.hosts]
		self.ready_voices()
		if not run_immedietly: return
		if hasattr(self, "do_configuration_interface"): self.configuration_interface()
		else: self.run()
	def handle_argv(self):
		p = argparse.ArgumentParser(argument_default = argparse.SUPPRESS)
		p.add_argument("--config", nargs = "?", const = "interface")
		p.add_argument("--hosts", nargs = "+")
		self.args_parsed = p.parse_args(sys.argv[1:])
		if "hosts" in self.args_parsed: self.hosts = self.args_parsed["hosts"]
		if "config" in self.args_parsed:
			if self.args_parsed.config == "interface": self.do_configuration_interface = True
			else: self.config_filename = self.args_parsed["config"]
	def get_voices(self):
		"""Must be implemented by subclasses. May return a string for a single voiced provider, a list of voice names, or a dictionary with the key being full voice names and the value being a subdictionary with any extra metadata."""
		return {}
	def ready_voices(self):
		"""Retrieves the list of voices by calling self.get_voices() and prepares/filters it for use."""
		self.voices = {}
		raw_voices = self.get_voices()
		if type(raw_voices) == list: raw_voices = dict.fromkeys(raw_voices, None)
		elif type(raw_voices) == str: raw_voices = {raw_voices: {}}
		for k in raw_voices:
			if not raw_voices[k]: raw_voices[k] = {}
			id = k.replace("_", " ").replace("-", " ").replace("(", " ").replace(")", " ").replace(":", " ").replace(".", "").replace("   ", " ").replace("  ", " ").strip()
			conf = self.config["voices"][id] if "voices" in self.config and id in self.config["voices"] else {}
			self.voices[id] = raw_voices[k]
			self.voices[id].update({"id": id, "full_name": k, "label": conf["alias"] if "alias" in conf else id, "enabled": conf.as_bool("enabled") if "enabled" in conf else True})
			if "alias" in conf: self.voices[id]["alias"] = conf["alias"]
	async def synthesize(self, voice, text, rate = None, pitch = None):
		"""Synthesizes some text, should return a bytes object containing the audio data (usually a playable wav file), or a string with an error message. The default implementation uses the executable and arguments defined by self.synthesis_process, allowing any providers that use external applications to be implemented almost instantly!"""
		if not hasattr(self, "synthesis_process"): return f"no method provided for synthesis of {voice}"
		try:
			with tempfile.NamedTemporaryFile(delete=False) as fp:
				fp.close()
			args = []
			for arg in self.synthesis_process: args.append(arg.format(voice = voice, text = text, rate = rate if rate is not None else 0, pitch = pitch if pitch is not None else 0, filename = fp.name))
			if rate is not None and hasattr(self, "synthesis_process_rate"):
				for arg in self.synthesis_process_rate: args.append(arg.format(rate = rate))
			if pitch is not None and hasattr(self, "synthesis_process_pitch"):
				for arg in self.synthesis_process_pitch: args.append(arg.format(pitch = pitch))
			print(args)
			process = await asyncio.create_subprocess_exec(*args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags = subprocess.CREATE_NO_WINDOW)
			await process.communicate()
			wave_data = b""
			with open(fp.name, "rb") as f: wave_data = f.read()
			os.unlink(fp.name)
			return wave_data
		except Exception as e:
			return str(e)
	async def connect(self, host):
		should_exit = False
		while not should_exit:
			try:
				async with websockets.asyncio.client.connect(host, max_size = None, max_queue = 4096) as websocket:
					connected_voices = await self.send_voices(websocket)
					print(f"Connected {connected_voices} voices to {host}.")
					while True:
						message = await websocket.recv()
						try:
							event = json.loads(message)
							asyncio.create_task(self.process_remote_event(websocket, event))
						except json.JSONDecodeError:
							print("Received an invalid JSON message:", message)
			except KeyboardInterrupt:
				print("shutting down")
				should_exit = True
			except Exception as e:
				traceback.print_exc()
				print(f"reconnecting to {host}... {e}")
				time.sleep(3)
	async def send_voices(self, websocket):
		"""Send a list of voice names to the server."""
		packet = {"provider": PROVIDER_REVISION, "voices": []}
		for v in self.voices:
			if not self.voices[v]["enabled"]: continue
			packet["voices"].append(self.voices[v]["label"])
		await websocket.send(json.dumps(packet))
		return len(packet["voices"])
	async def process_remote_event(self, websocket, event):
		"""Receives a JSON payload from the coagulator and processes it, sending back either synthesized audio or an error payload."""
		try:
			if "voice" in event and "text" in event:
				synthesis_result = None
				if not event["voice"] in self.voices: synthesis_result = f"cannot find voice {event['voice']}"
				else: synthesis_result = await self.synthesize(self.voices[event["voice"]]["full_name"], event["text"], event["rate"] if "rate" in event else None, event["pitch"] if "pitch" in event else None)
				if type(synthesis_result) == str: await websocket.send(json.dumps({"provider": PROVIDER_REVISION, "id": event["id"], "status": synthesis_result, "abort": True}))
				else: await websocket.send(len(event["id"]).to_bytes(2, "little") + event["id"].encode() + synthesis_result)
		except Exception as e:
			await websocket.send(json.dumps({"provider": PROVIDER_REVISION, "id": event["id"], "status": f"exception during synthesis {e}", "abort": True}))
	async def async_main(self):
		await asyncio.gather(*[self.connect(host) for host in self.hosts])
	def run(self):
		while True:
			try:
				asyncio.run(self.async_main())
			except KeyboardInterrupt:
				print("shutting down")
				break
			except Exception as e:
				traceback.print_exc()
				print("reconnecting... {e}")
				time.sleep(10)
	def configuration_interface(self):
		star_provider_configurator(self).main_loop()

