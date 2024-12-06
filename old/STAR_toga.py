# One plan I had was to rewrite the STAR client using the Toga UI library. Unfortunately after I started I ran into several limitations with the library, from not being able to tell what control was focused to not being able to determine the selection of a text field to the lacking of good keyboard shortcut support. This is an archive of the code I did write for this client before determining that I might as well rewrite the STAR client with WX.

import accessible_output2.outputs.auto
import asyncio
import atexit
import configobj
import json
import miniaudio
import os
import time
import toga
import traceback
import websockets.asyncio.client

USER_REVISION = 3

speech = accessible_output2.outputs.auto.Auto()

class playsound:
	"""A small and very basic wrapper around pyminiaudio that gives us a basic audio stream class with pause, pitch, and end callback functionality. Pyminiaudio only wraps miniaudio's lowest level API, so we need something that couple's it's device and stream classes together."""
	def __init__(self, data, pitch = 1.0, finish_func = None, finish_func_data = None):
		self.finish_func = finish_func
		self.finish_func_data = finish_func_data
		self.device = miniaudio.PlaybackDevice(buffersize_msec = 5, sample_rate = int(44100 * pitch))
		atexit.register(self.device.close)
		if type(data) == bytes: self.stream = miniaudio.stream_with_callbacks(miniaudio.stream_memory(data), end_callback = self.on_stream_end)
		else: self.stream = miniaudio.stream_with_callbacks(miniaudio.stream_file(data, sample_rate = 44100), end_callback = self.on_stream_end)
		next(self.stream)
		self.device.start(self.stream)
	def __del__(self): self.close()
	def on_stream_end(self):
		self.close()
		if self.finish_func: self.finish_func(self.finish_func_data)
	@property
	def playing(self): return self.device is not None and self.device.running
	def pause(self):
		if not self.playing: return False
		self.device.stop()
		return True
	def resume(self):
		if not self.device or self.playing: return False
		self.device.start(self.stream)
		return True
	def close(self):
		if not self.device: return
		atexit.unregister(self.device.close)
		self.device.close()
		self.device = None

class star_client(toga.App):
	def __init__(self):
		toga.App.__init__(self, "STAR client", "com.samtupy.STARUser", author = "Sam Tupy Productions", version = f"{USER_REVISION}", home_page = "https://samtupy.com/star", description = "The Speech To Audio Relay user client is responsible for providing an interface for users to request remote speech synthesis to then be rendered into audio files or played back.")
		self.initial_connection = False
		self.speech_cache = {}
	def startup(self):
		self.main_window  = toga.MainWindow()
		voices_label = toga.Label("&Voices")
		self.voices_list = toga.Table(headings = ["name"])
		self.quickspeak_box = toga.Box(children = [voices_label, self.voices_list])
		self.script_box = toga.Box(children = [voices_label, self.voices_list])
		self.settings_box = toga.Box()
		self.connecting_box = toga.Box(children = [toga.Label("Connecting...")])
		self.tabs = toga.OptionContainer(content = [("Connecting...", self.connecting_box), ("Settings", self.settings_box)])
		quickspeak_label = toga.Label("&quickspeak")
		self.quickspeak = toga.TextInput()
		self.quickspeak_box.add(quickspeak_label, self.quickspeak)
		script_label = toga.Label("Enter &script")
		self.script = toga.MultilineTextInput()
		render_btn = toga.Button("&Render to wav", on_press = self.on_render)
		self.script_box.add(script_label, self.script, render_btn)
		exit_btn = toga.Button("E&xit", on_press = self.on_exit_btn)
		preview_prev = toga.Command(self.on_preview_prev, text = "preview previous line", shortcut = toga.Key.MOD_1 + toga.Key.MOD_2 + "<up>")
		preview_next = toga.Command(self.on_preview_next, text = "preview next line", shortcut = toga.Key.MOD_1 + toga.Key.MOD_2 + "<down>")
		self.commands.add(preview_prev, preview_next)
		self.app_box = toga.Box(children = [self.tabs, exit_btn])
		self.main_window.content = self.app_box
		self.main_window.show()
	async def on_render(self, button): pass
	def on_exit_btn(self, button): self.request_exit()
	async def on_running(self):
		asyncio.create_task(self.connect("ws://samtupy.com:7774"))
	def on_preview_prev(self, command):
		sel = self.script._impl.native.SelectionStart;
		if sel < 0 or sel > len(self.script.value): return
		if sel: sel -= 2
		while sel >= 0 and self.script.value[sel] != "\n": sel -= 1
		if sel: sel += 1
		self.script._impl.native.SelectionStart = sel
	async def on_preview_next(self, command): pass
	async def connect(self, host):
		should_exit = False
		while not should_exit:
			try:
				async with websockets.asyncio.client.connect(host, max_size = None, max_queue = 4096) as websocket:
					await self.on_connect(websocket)
					while True:
						message = await websocket.recv()
						try:
							event = json.loads(message)
							self.on_remote_message(websocket, event)
						except json.JSONDecodeError:
							print("Received an invalid JSON message:", message)
			except KeyboardInterrupt:
				print("shutting down")
				should_exit = True
			except Exception as e:
				traceback.print_exc()
				print(f"reconnecting to {host}... {e}")
				time.sleep(3)
	async def on_connect(self, websocket):
		await websocket.send(json.dumps({"user": USER_REVISION}))
		if not self.initial_connection:
			self.initial_connection = True
			self.tabs.content.insert(1, "Script", self.script_box)
			self.tabs.content.insert(2, "Quickspeak", self.quickspeak_box)
			self.tabs.current_tab = 1
			self.script.focus()
			self.tabs.content.remove(0)
			playsound("audio/ready.ogg");
	def on_remote_message(self, websocket, message):
		if "voices" in message:
			playsound("audio/voices_connect.ogg")
			self.voices_list.data = [(i) for i in message["voices"]]


if __name__ == "__main__":
	star_client().main_loop()
