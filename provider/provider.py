# This is the base provider class for STAR and implements as many common features as possible.

PROVIDER_REVISION = 4

import argparse
import asyncio
import configobj
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import time
import traceback
import websockets.asyncio.client
import wx

class voice_edit_dialog(wx.Dialog):
	"""This is a subdialog of the below star_provider_configurator dialog which handles editing properties for a single voice."""
	def __init__(self, parent, voice = {}):
		wx.Dialog.__init__(self, parent, title = "Edit Voice")
		self.CreateButtonSizer(wx.OK | wx.CANCEL)
		self.enabled = wx.CheckBox(self, label = "&Enable Voice")
		self.enabled.Value = voice["enabled"] if "enabled" in voice else True
		wx.StaticText(self, -1, "Voice &Alias")
		self.alias = wx.TextCtrl(self, value = voice["alias"] if "alias" in voice else "")
		self.enabled.SetFocus()
	def dump(self, v):
		"""Writes the user provided values to the given voice item."""
		v["enabled"] = self.enabled.Value
		if self.alias.Value: v["alias"] = self.alias.Value
		elif "alias" in v: del(v["alias"])

class voices_list(wx.ListCtrl):
	"""The voices list is implemented in virtual mode as it may contain a large number of items and , this class facilitates that."""
	def __init__(self, parent, *args, **kwargs):
		wx.ListCtrl.__init__(self, parent, *args, **kwargs)
		self.AppendColumn("voice name")
		self.AppendColumn("Enabled")
		self.AppendColumn("Alias")
		self.SetItemCount(len(parent.provider.voices))
		self.voice_names = list(parent.provider.voices)
	def OnGetItemText(self, item, column):
		v = self.Parent.provider.voices[self.voice_names[item]]
		if column == 0: return self.voice_names[item]
		elif column == 1: return "Yes" if v["enabled"] else "No"
		elif column == 2: return v["alias"] if "alias" in v else ""

class star_provider_configurator(wx.Dialog):
	"""This dialog allows for a GUI based method of configuring all aspects of a provider."""
	def __init__(self, provider):
		wx.Dialog.__init__(self, None, title = "STAR Provider Configuration")
		self.provider = provider
		self.CreateButtonSizer(wx.OK | wx.CANCEL)
		wx.StaticText(self, -1, "&Hosts")
		self.hosts_list = wx.ListCtrl(self, style = wx.LC_SINGLE_SEL | wx.LC_REPORT)
		self.hosts_list.AppendColumn("Host")
		for h in provider.hosts: self.hosts_list.Append([h])
		delete_host_id = wx.NewIdRef()
		self.hosts_list.Bind(wx.EVT_MENU, self.on_delete_host, id = delete_host_id)
		self.hosts_list.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_NORMAL, wx.WXK_DELETE, delete_host_id)]))
		self.hosts_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit_host)
		wx.Button(self, label = "&New host...").Bind(wx.EVT_BUTTON, self.on_new_host)
		wx.StaticText(self, -1, "&Voices")
		self.voices_list = voices_list(self, style = wx.LC_SINGLE_SEL | wx.LC_REPORT | wx.LC_VIRTUAL)
		self.voices_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_edit_voice)
		wx.StaticText(self, -1, "Number of &concurrent requests")
		self.concurrent_requests = wx.SpinCtrl(self, value = str(int(provider.config.get("concurrent_requests", multiprocessing.cpu_count() / 2))), min = 1, max = multiprocessing.cpu_count() * 4)
		provider.add_configuration_options(self)
		self.hosts_list.Focus(0)
		self.hosts_list.SetFocus()
	def host_dlg(self, value = ""):
		dlg = wx.TextEntryDialog(self, "Host", "Enter a valid websocket URI E. ws://127.0.0.1:7774", value)
		if dlg.ShowModal() != wx.ID_OK: return ""
		return dlg.Value
	def on_new_host(self, evt):
		h = self.host_dlg()
		if not h: return
		self.hosts_list.Append([h])
		self.hosts_list.SetFocus()
	def on_edit_host(self, evt):
		h = self.host_dlg(evt.Label)
		if not h: return
		self.hosts_list.SetItemText(evt.Index, h)
		self.hosts_list.SetFocus()
	def on_delete_host(self, evt):
		h = self.hosts_list.FocusedItem
		if h < 0: return
		self.hosts_list.DeleteItem(h)
	def on_edit_voice(self, evt):
		dlg = voice_edit_dialog(self, self.provider.voices[self.voices_list.voice_names[evt.Index]])
		if dlg.ShowModal() != wx.ID_OK: return
		dlg.dump(self.provider.voices[self.voices_list.voice_names[evt.Index]])
	def save(self):
		c = configobj.ConfigObj(self.provider.config_filename)
		c["hosts"] = [self.hosts_list.GetItemText(i) for i in range(self.hosts_list.GetItemCount())]
		c["concurrent_requests"] = self.concurrent_requests.Value
		for voice in self.provider.voices:
			voice = self.provider.voices[voice]
			if not voice["enabled"] or "alias" in voice and voice["alias"]:
				if not "voices" in c: c["voices"] = {}
				c["voices"][voice["id"]] = {"alias": voice["alias"] if "alias" in voice else "", "enabled": voice["enabled"]}
			elif "voices" in c and voice["id"] in c["voices"]: del(c["voices"][voice["id"]])
		self.provider.write_configuration_options(self, c)
		c.write()

class star_provider:
	"""A base class that can be used to implement any STAR provider able to be written in Python3. It abstracts all communication with coagulators, as much of the async stuff as possible, filtering voice names and more."""
	def __init__(self, provider_basename = os.path.splitext(sys.argv[0])[0], handle_argv = True, run_immedietly = True, voices = None, synthesis_process = None, synthesis_process_rate = None, synthesis_process_pitch = None, synthesis_default_rate = None, synthesis_default_pitch = None, synthesis_audio_extension = None):
		"""The provider_basename argument should be set to a simple strings such as balcony or pyttsx. Set handle_argv to False if you don't wish for the default CLI interface. If you really wish to configure this object further than the constructor allows before running the provider, set run_immedietly to False. The default implementation makes it easy to implement executable based providers with  the synthesis_process arguments."""
		self.config_filename = f"{provider_basename}.ini"
		self.basename = provider_basename
		if voices: self.initial_voices = voices
		if synthesis_process: self.synthesis_process = synthesis_process
		if synthesis_process_rate: self.synthesis_process_rate = synthesis_process_rate
		if synthesis_process_pitch: self.synthesis_process_pitch = synthesis_process_pitch
		self.synthesis_default_rate = synthesis_default_rate
		self.synthesis_default_pitch = synthesis_default_pitch
		self.synthesis_audio_extension = synthesis_audio_extension
		if handle_argv: self.handle_argv()
		self.config = configobj.ConfigObj(self.config_filename)
		if not hasattr(self, "hosts"): self.hosts = self.config.get("hosts", ["ws://localhost:7774"])
		if type(self.hosts) == str: self.hosts = [self.hosts]
		self.read_configuration_options()
		self.canceled_requests = set()
		self.ready_voices()
		if run_immedietly: self.run()
	def handle_argv(self):
		p = argparse.ArgumentParser(argument_default = argparse.SUPPRESS)
		p.add_argument("--config", nargs = "?", const = self.config_filename)
		p.add_argument("--configure", action = "store_true")
		p.add_argument("--hosts", nargs = "+")
		self.args_parsed = p.parse_args(sys.argv[1:])
		if "hosts" in self.args_parsed: self.hosts = self.args_parsed.hosts
		if "configure" in self.args_parsed: self.do_configuration_interface = True
		if "config" in self.args_parsed: self.config_filename = self.args_parsed.config
	def get_voices(self):
		"""Usually  implemented by subclasses. May return a string for a single voiced provider, a list of voice names, or a dictionary with the key being full voice names and the value being a subdictionary with any extra metadata. The default implementation just returns self.initial_voices (set in the constructor) as a shortcut for very simple providers."""
		return self.initial_voices
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
			self.voices[id].update({"id": id, "full_name": self.voices[id]["full_name"] if "full_name" in self.voices[id] else k, "label": conf["alias"] if "alias" in conf else id, "enabled": conf.as_bool("enabled") if "enabled" in conf else True})
			if "alias" in conf: self.voices[id]["alias"] = conf["alias"]
	async def synthesize(self, voice, text, rate = None, pitch = None):
		"""Synthesizes some text, should return a bytes object containing the audio data (usually a playable wav file or other common audio format), otherwise a string with an error message. The default implementation uses the executable and arguments defined by self.synthesis_process, allowing any providers that use external applications to be implemented almost instantly!"""
		if not hasattr(self, "synthesis_process"): return f"no method provided for synthesis of {voice}"
		try:
			with tempfile.NamedTemporaryFile(suffix=f".{self.synthesis_audio_extension if self.synthesis_audio_extension else 'wav'}", delete=False) as fp:
				fp.close()
			args = []
			for arg in self.synthesis_process: args.append(arg.format(voice = voice, text = text.replace("\"", " "), rate = rate if rate is not None else 0, pitch = pitch if pitch is not None else 0, filename = fp.name))
			if rate is not None and hasattr(self, "synthesis_process_rate"):
				for arg in self.synthesis_process_rate: args.append(arg.format(rate = rate))
			if pitch is not None and hasattr(self, "synthesis_process_pitch"):
				for arg in self.synthesis_process_pitch: args.append(arg.format(pitch = pitch))
			process = await asyncio.create_subprocess_exec(*args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
			await process.communicate()
			audio_data = b""
			with open(fp.name, "rb") as f: audio_data = f.read()
			os.unlink(fp.name)
			return audio_data
		except Exception as e:
			return str(e)
	async def connect(self, host):
		should_exit = False
		last_exception = ""
		while not should_exit:
			try:
				async with websockets.asyncio.client.connect(host, max_size = None, max_queue = 4096) as websocket:
					connected_voices = await self.send_voices(websocket)
					print(f"Connected {connected_voices} voices to {host}.")
					while True:
						message = await websocket.recv()
						try:
							event = json.loads(message)
							if "abort" in event: self.canceled_requests.add(event["abort"])
							else: await self.task_queue.put((websocket, event))
						except json.JSONDecodeError:
							print("Received an invalid JSON message:", message)
			except KeyboardInterrupt:
				print("shutting down")
				should_exit = True
			except Exception as e:
				exc = str(e)
				if exc != last_exception:
					if not isinstance(e, ConnectionRefusedError): traceback.print_exc()
					print(f"reconnecting to {host}... {e}")
				last_exception = exc
				time.sleep(3)
	async def send_voices(self, websocket):
		"""Send a list of voice names to the server."""
		packet = {"provider": PROVIDER_REVISION, "provider_name": self.basename, "voices": []}
		for v in self.voices:
			if not self.voices[v]["enabled"]: continue
			packet["voices"].append(self.voices[v]["label"])
		await websocket.send(json.dumps(packet))
		return len(packet["voices"])
	async def process_remote_event(self, websocket, event):
		"""Receives a JSON payload from the coagulator and processes it, sending back either synthesized audio or an error payload."""
		try:
			if "voice" in event and "text" in event:
				if event["id"] in self.canceled_requests:
					self.canceled_requests.remove(event["id"])
					return
				synthesis_result = None
				if not event["voice"] in self.voices: synthesis_result = f"cannot find voice {event['voice']}"
				else: synthesis_result = await self.synthesize(self.voices[event["voice"]]["full_name"], event["text"], event["rate"] if "rate" in event else self.synthesis_default_rate, event["pitch"] if "pitch" in event else self.synthesis_default_pitch)
				meta = {"id": event["id"]}
				if self.synthesis_audio_extension: meta["extension"] = self.synthesis_audio_extension
				meta = json.dumps(meta)
				if type(synthesis_result) == str: await websocket.send(json.dumps({"provider": PROVIDER_REVISION, "id": event["id"], "status": synthesis_result, "abort": True}))
				else: await websocket.send(len(meta).to_bytes(2, "little") + meta.encode() + synthesis_result)
		except Exception as e:
			traceback.print_exc()
			await websocket.send(json.dumps({"provider": PROVIDER_REVISION, "id": event["id"], "status": f"exception during synthesis {e}", "abort": True}))
	async def handle_task_queue(self):
		while True:
			event = await self.task_queue.get()
			await self.process_remote_event(*event)
			self.task_queue.task_done()
	async def async_main(self):
		self.task_queue = asyncio.LifoQueue()
		for i in range(int(self.config.get("concurrent_requests", multiprocessing.cpu_count() / 2))): asyncio.create_task(self.handle_task_queue())
		await asyncio.gather(*[self.connect(host) for host in self.hosts])
	def run(self):
		if hasattr(self, "do_configuration_interface"): return self.configuration_interface()
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
	def add_configuration_options(self, panel):
		"""Override this in subclasses to add options to the GUI configurator."""
	def read_configuration_options(self):
		"""Override this in subclasses if needed to read custom options from the configuration file before get_voices is called for the first time."""
	def write_configuration_options(self, panel, config):
		"""Override this in subclasses to save any custom conffiguration options to the ini file when the user clicks the same button in the GUI configurator."""
	def configuration_interface(self):
		if not wx.GetApp(): app = wx.App()
		c = star_provider_configurator(self)
		if c.ShowModal() == wx.ID_OK: c.save()

if __name__ == "__main__":
	print("Warning, this script is not meant to be run directly, it serves as the base class for all python based STAR providers.\nYou probably want to run balcony.py, macsay.py etc instead both to run and configure each provider.")
