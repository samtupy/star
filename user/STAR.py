import accessible_output2.outputs.auto
import asyncio
import atexit
import configobj
import json
import miniaudio
import os
import time
import traceback
import websockets.asyncio.client
import wx
from wxasync import AsyncBind, WxAsyncApp, StartCoroutine, AsyncShowDialogModal

USER_REVISION = 3

speech = accessible_output2.outputs.auto.Auto()
config = configobj.ConfigObj("STAR.ini")

def is_valid_ws_uri(uri):
	"""Helper function to insure a provided host is basically a valid websocket URI. Returns either True or an error string, doesn't really do all that much validation right now."""
	if not uri: return "must not be empty"
	if not uri.startswith("ws://") and not uri.startswith("wss://"): return "must start with a valid scheme (ws or wss)"
	return True

class playsound:
	"""A small and very basic wrapper around pyminiaudio that gives us a basic audio stream class with pause, pitch, and end callback functionality. Pyminiaudio only wraps miniaudio's lowest level API, so we need something that couple's it's device and stream classes together."""
	def __init__(self, data, pitch = 1.0, finish_func = None, finish_func_data = None):
		self.finish_func = finish_func
		self.finish_func_data = finish_func_data
		self.device = miniaudio.PlaybackDevice(buffersize_msec = 5, sample_rate = int(44100 * pitch))
		atexit.register(self.device.close)
		if type(data) == bytes: self.stream = miniaudio.stream_with_callbacks(miniaudio.stream_memory(data, sample_rate = 44100), end_callback = self.on_stream_end)
		else: self.stream = miniaudio.stream_with_callbacks(miniaudio.stream_file(data, sample_rate = 44100), end_callback = self.on_stream_end)
		next(self.stream)
		self.device.start(self.stream)
	def __del__(self): self.close()
	def on_stream_end(self):
		if self.finish_func: self.finish_func(self.finish_func_data)
		self.close() # must call below finish_func or finish_func doesn't fire
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

class speech_request:
	"""Container class which stores various bits of information we wish to remember about an outgoing speech request."""
	next_request_id = 1
	def __init__(self, textline, render_sequence = 0):
		self.textline = textline
		self.render_sequence = render_sequence
		self.request_id = str(speech_request.next_request_id)
		speech_request.next_request_id += 1

class voices_list(wx.ListCtrl):
	def OnGetItemText(self, item, column):
		if column == 0: return self.main_frame.voices[item]
	def update(self, main_frame):
		self.main_frame = main_frame
		self.SetItemCount(len(main_frame.voices))
		self.Refresh()

EVT_DONE_SPEAKING = wx.Window.NewControlId()
class done_speaking_event(wx.PyEvent):
	def __init__(self, data = None):
		wx.PyEvent.__init__(self)
		self.SetEventType(EVT_DONE_SPEAKING)
		self.data = data

class star_client_configuration(wx.Dialog):
	def __init__(self, parent):
		wx.Dialog.__init__(self, parent, title = "STAR Client Configuration")
		host_label = wx.StaticText(self, -1, "&Host to connect to")
		self.host = wx.TextCtrl(self, value = config.get("host", ""))
		render_path_label = wx.StaticText(self, -1, "Default &Render location")
		self.render_path = wx.DirPickerCtrl(self, path = config.get("render_path", os.path.join(os.getcwd(), "output")), message = "Select a default directory to render output into")
		render_path_label.Reparent(self.render_path)
		self.clear_cache_btn = wx.Button(self, label = "&Clear audio cache")
		self.clear_cache_btn.Bind(wx.EVT_BUTTON, self.on_clear_cache)
		self.clear_cache_btn.Enabled = hasattr(parent, "speech_cache") and len(parent.speech_cache) > 0
		self.CreateButtonSizer(wx.OK | wx.CANCEL)
		self.Bind(wx.EVT_SHOW, self.on_show)
	def on_show(self, evt):
		self.host.SetFocus()
	def on_clear_cache(self, evt):
		self.Parent.speech_cache = {}
		self.clear_cache_btn.Enabled = False
	async def validate(self):
		is_uri = is_valid_ws_uri(self.host.Value)
		if type(is_uri) == str:
			await AsyncShowDialogModal(wx.MessageDialog(self, f"host {is_uri}", "error"))
			self.host.SetFocus()
			return False
		return True

class star_client(wx.Frame):
	def __init__(self, parent = None):
		wx.Frame.__init__(self, parent, title = "STAR Client")
		self.configuration = star_client_configuration(self)
		self.main_panel = wx.Panel(self)
		self.connecting_panel = wx.Panel(self)
		self.connecting_label = wx.StaticText(self.connecting_panel, -1, "Connecting..." if "host" in config else "Host not configured.")
		connecting_options_btn = wx.Button(self.connecting_panel, label = "&Options")
		AsyncBind(wx.EVT_BUTTON, self.on_options, connecting_options_btn)
		sizer = wx.BoxSizer()
		voices_label = wx.StaticText(self.main_panel, -1, "&Voices")
		self.voices_list = voices_list(self.main_panel, style = wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
		AsyncBind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_preview_voice, self.voices_list)
		copy_voicename_id = wx.NewIdRef()
		self.Bind(wx.EVT_MENU, self.on_copy_voicename, id = copy_voicename_id)
		self.voices_list.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('c'), copy_voicename_id)]))
		quickspeak_label = wx.StaticText(self.main_panel, -1, "&Quickspeak")
		self.quickspeak = wx.TextCtrl(self.main_panel, style = wx.TE_PROCESS_ENTER | wx.TE_MULTILINE | wx.HSCROLL)
		AsyncBind(wx.EVT_TEXT_ENTER, self.on_quickspeak, self.quickspeak)
		script_label = wx.StaticText(self.main_panel, -1, "Enter &Script")
		self.script = wx.TextCtrl(self.main_panel, size = (1024, 512), style = wx.TE_MULTILINE | wx.TE_RICH2 | wx.HSCROLL)
		self.preview_prev_id = wx.NewIdRef()
		self.preview_next_id = wx.NewIdRef()
		self.preview_cur_id = wx.NewIdRef()
		self.preview_continuous_id = wx.NewIdRef()
		AsyncBind(wx.EVT_MENU, self.on_preview_script, self, id = self.preview_prev_id)
		AsyncBind(wx.EVT_MENU, self.on_preview_script, self, id = self.preview_next_id)
		AsyncBind(wx.EVT_MENU, self.on_preview_script, self, id = self.preview_cur_id)
		AsyncBind(wx.EVT_MENU, self.on_preview_script, self, id = self.preview_continuous_id)
		self.script.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL | wx.ACCEL_ALT, ord(' '), self.preview_cur_id), (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_UP, self.preview_prev_id), (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_DOWN, self.preview_next_id), (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_RETURN, self.preview_continuous_id)]))
		render_btn = wx.Button(self.main_panel, label = "&Render to wav")
		options_btn = wx.Button(self.main_panel, label = "&Options")
		AsyncBind(wx.EVT_BUTTON, self.on_options, options_btn)
		exit_btn = wx.Button(self.main_panel, label = "E&xit")
		exit_btn.Bind(wx.EVT_BUTTON, self.on_exit_btn)
		sizer.Add(voices_label, 0, wx.ALL, 5)
		sizer.Add(self.voices_list, 0, wx.ALL, 5)
		sizer.Add(quickspeak_label, 0, wx.ALL, 5)
		sizer.Add(self.quickspeak, 0, wx.ALL, 5)
		sizer.Add(script_label, 0, wx.ALL, 5)
		sizer.Add(self.script, 0, wx.ALL, 5)
		sizer.Add(render_btn, 0, wx.ALL, 5)
		sizer.Add(options_btn, 0, wx.ALL, 5)
		sizer.Add(exit_btn, 0, wx.ALL, 5)
		self.main_panel.SetSizer(sizer)
		stop_speaking_id = wx.NewIdRef()
		self.main_panel.Bind(wx.EVT_MENU, self.on_stop_speaking, id = stop_speaking_id)
		self.main_panel.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_ALT, wx.WXK_BACK, stop_speaking_id)]))
		self.Connect(-1, -1, EVT_DONE_SPEAKING, self.on_auto_preview_next_script_line)
		self.main_panel.Hide()
		self.connecting_panel.Show()
		self.connecting_label.SetFocus()
		self.voices_list.InsertColumn(0, "voice name")
		self.voices = []
		self.speech_requests = {}
		self.speech_cache = {}
		self.current_speech = None
		self.initial_connection = False
		self.script_continuous_preview = False
		self.Show()
		self.connection_task = StartCoroutine(self.connect(config.get("host", "")), self)
	def on_copy_voicename(self, evt):
		voice = self.voices_list.FocusedItem
		if voice < 0 or voice >= len(self.voices):
			speech.speak("not focused on a voice")
			return
		if wx.TheClipboard.Open():
			wx.TheClipboard.SetData(wx.TextDataObject(self.voices[voice]))
			wx.TheClipboard.Close()
		speech.speak("copied")
	async def on_preview_voice(self, evt):
		await self.audiospeak(f"{evt.Label}: Hello there, my name is {evt.Label}.")
	async def on_quickspeak(self, evt):
		voice = self.voices_list.FocusedItem
		if voice < 0 or voice >= len(self.voices):
			speech.speak("not focused on a voice")
			return
		if not self.quickspeak.Value:
			speech.speak("nothing to speak")
			return
		await self.audiospeak(f"{self.voices[voice]}: {self.quickspeak.Value.replace("\n", "  ")}")
	async def on_preview_script(self, evt):
		pos = self.script.GetInsertionPoint()
		b, col, line = self.script.PositionToXY(pos)
		if evt.Id == self.preview_prev_id: line -= 1
		elif evt.Id == self.preview_next_id: line += 1
		line_len = self.script.GetLineLength(line)
		if line_len < 0: return
		new_pos = self.script.XYToPosition(0, line)
		if pos != new_pos: self.script.SetInsertionPoint(new_pos)
		self.script_continuous_preview = evt.Id == self.preview_continuous_id
		line_text = self.script.GetLineText(line).strip()
		if not line_text or line_text.startswith(";"): return
		await self.audiospeak(line_text)
	def on_auto_preview_next_script_line(self, evt):
		text = ""
		b, col, line = self.script.PositionToXY(self.script.GetInsertionPoint())
		while not text:
			line += 1
			line_len = self.script.GetLineLength(line)
			if line_len < 0:
				self.script_continuous_preview = False
				return
			self.script.SetInsertionPoint(self.script.XYToPosition(0, line))
			text = self.script.GetLineText(line).strip()
			if not text or text.startswith(";"):
				text = ""
				continue
		StartCoroutine(self.audiospeak(text), self)
	async def on_options(self, evt = None):
		while True:
			r = await AsyncShowDialogModal(self.configuration)
			if r != wx.ID_OK: break
			if not await self.configuration.validate(): continue
			old_host = config.get("host", "")
			config["host"] = self.configuration.host.Value
			if old_host != config["host"]: self.reconnect()
			config.write()
			break
		if self.initial_connection: self.main_panel.SetFocus()
		else: self.connecting_panel.SetFocus()
	def on_exit_btn(self, evt): self.Close()
	def on_stop_speaking(self, evt):
		if not self.current_speech: return
		self.current_speech.close()
		self.current_speech = None
		self.script_continuous_preview = False
	def reconnect(self):
		if self.connection_task: self.connection_task.cancel()
		self.initial_connection = False
		self.speech_requests = {}
		self.voices = {}
		self.voices_list.update(self)
		self.connecting_label.Label = "Connecting..."
		self.connecting_panel.Show()
		self.connecting_panel.SetFocus()
		self.connecting_label.SetFocus()
		self.main_panel.Hide()
		self.connection_task = StartCoroutine(self.connect(config.get("host", "")), self)
	async def connect(self, host):
		if not host: return
		should_exit = False
		while not should_exit:
			try:
				async with websockets.asyncio.client.connect(host, max_size = None, max_queue = 4096) as websocket:
					await self.on_connect(websocket)
					while True:
						message = await websocket.recv()
						if type(message) == bytes:
							self.on_remote_binary(websocket, message)
						else:
							try:
								event = json.loads(message)
								self.on_remote_message(websocket, event)
							except json.JSONDecodeError:
								print("Received an invalid JSON message:", message)
			except KeyboardInterrupt:
				print("shutting down")
				should_exit = True
			except websockets.exceptions.InvalidURI as e:
				print("warning,", e)
				return
			except Exception as e:
				traceback.print_exc()
				print(f"reconnecting to {host}... {e}")
				asyncio.sleep(3)
	async def on_connect(self, websocket):
		await websocket.send(json.dumps({"user": USER_REVISION}))
		self.websocket = websocket
		if not self.initial_connection:
			self.initial_connection = True
			self.connecting_panel.Hide()
			self.main_panel.Show()
			self.main_panel.SetFocus()
	def on_remote_binary(self, websocket, message):
		if len(message) < 4: return
		id_len = int.from_bytes(message[:2], "little")
		id = message[2:id_len+2].partition(b"_")[2].partition(b"_")[0].decode()
		self.on_remote_audio(id, message[id_len+2:])
	def on_remote_message(self, websocket, message):
		if "voices" in message:
			playsound("audio/ready.ogg")
			if len(message["voices"]) > len(self.voices): playsound("audio/voices_connect.ogg")
			elif len(message["voices"]) < len(self.voices): playsound("audio/voices_disconnect.ogg")
			focused_voice = self.voices_list.FocusedItem
			if focused_voice > -1 and focused_voice < len(self.voices): focused_voice = self.voices[focused_voice]
			else: focused_voice = 0
			self.voices = message["voices"]
			self.voices_list.update(self)
			if type(focused_voice) == str: focused_voice = self.voices_list.FindItem(0, focused_voice)
			if len(self.voices) > 0 and focused_voice > -1 and self.voices_list.FocusedItem != focused_voice:
				self.voices_list.Select(focused_voice)
				self.voices_list.Focus(focused_voice)
		elif "error" in message:
			playsound("audio/error.ogg")
			speech.speak(message["error"])
		elif "warning" in message:
			playsound("audio/warning.ogg")
			speech.speak(message["warning"])
	def on_remote_audio(self, id, audio):
		if not id in self.speech_requests: return # We should error about this somehow?
		r = self.speech_requests.pop(id)
		self.speech_cache[r.textline] = audio
		self.configuration.clear_cache_btn.Enabled = True
		if not r.render_sequence:
			if self.current_speech: self.current_speech.close()
			self.current_speech = playsound(audio, finish_func = self.on_done_speaking)
	def on_done_speaking(self, unused):
		self.current_speech = None
		if self.script_continuous_preview: wx.PostEvent(self, done_speaking_event())
	async def audiospeak(self, textline, render_sequence = 0):
		"""One of the main public interfaces in this application: Receives a parsable line of text "Sam: hello", and either plays the resulting speech synthesis or renders it if a sequence number is given."""
		if textline in self.speech_cache:
			if not render_sequence:
				if self.current_speech: self.current_speech.close()
				self.current_speech = playsound(self.speech_cache[textline], finish_func = self.on_done_speaking)
		else:
			r = speech_request(textline, render_sequence)
			self.speech_requests[r.request_id] = r
			await self.websocket.send(json.dumps({"user": USER_REVISION, "request": textline, "id": r.request_id}))

async def main():
	app = WxAsyncApp(sleep_duration = 0.001)
	client = star_client()
	await app.MainLoop()

asyncio.run(main())
