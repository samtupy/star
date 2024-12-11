import accessible_output2.outputs.auto
import asyncio
import atexit
import configobj
import glob
import json
import miniaudio
import os
from pydub import AudioSegment
import tempfile
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

def parse_textline(textline, aliases = {}):
	"""This utility function splits the provided line of script (Mike<r=2>: Hi there) into a tuple of voicename, params, text. Aliases is a dictionary of alias: full_voicename, and the returned voicename will be run through this replacement dictionary."""
	text = textline.partition(":")
	voicename = text[0].partition("<")
	params = "<" + voicename[2] if voicename[2] else ""
	voicename = voicename[0]
	if voicename.lower() in aliases: voicename = aliases[voicename.lower()]
	return (voicename, params, text[2].strip())

def slugify(text, space_replacement = "", char_passthroughs = [" ", "_", "-", ",", ".", "!"]):
	"""Utility to convert a string into a valid filename."""
	if space_replacement: text = text.replace(" ", space_replacement)
	new_text = ""
	for char in text:
		if char.isalnum() or char in char_passthroughs: new_text += char
	return new_text

ma_devices = miniaudio.Devices()
playsound_devices = ma_devices.get_playbacks()
playsound_device = None
def set_playsound_device(dev):
	global playsound_device
	if not dev:
		playsound_device = None
		return
	for d in playsound_devices:
		if d["name"] != dev: continue
		playsound_device = d["id"]
		break
set_playsound_device(config.get("output_device", None))

class playsound:
	"""A small and very basic wrapper around pyminiaudio that gives us a basic audio stream class with pause, pitch, and end callback functionality. Pyminiaudio only wraps miniaudio's lowest level API, so we need something that couple's it's device and stream classes together."""
	def __init__(self, data, pitch = 1.0, finish_func = None, finish_func_data = None):
		self.finish_func = finish_func
		self.finish_func_data = finish_func_data
		self.device = miniaudio.PlaybackDevice(buffersize_msec = 5, sample_rate = int(44100 * pitch), device_id = playsound_device)
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
	def __init__(self, textline, render_filename = None):
		self.timestamp = time.time()
		self.textline = textline
		self.render_filename = render_filename
		self.request_id = str(speech_request.next_request_id)
		speech_request.next_request_id += 1

render_filename_tokens = [
	("counter0", "A counter in the format 0, 1, 2...", lambda render: str(render.counter -1)),
	*[(f"counter{'0' * (i + 2)}", f"A counter in the format {', '.join([str(x).zfill(i + 2) for x in range(3)])}...", lambda render, i = i: str(render.counter -1).zfill(i + 2)) for i in range(3)],
	("counter1", "A counter in the format 1, 2, 3...", lambda render: str(render.counter)),
	*[(f"counter{'0' * (i + 1)}1", f"A counter in the format {', '.join([str(x + 1).zfill(i + 2) for x in range(3)])}...", lambda render, i = i: str(render.counter).zfill(i + 2)) for i in range(3)],
	*[(f"line{'0' * i}0", f"The item's 0-based line number in the format {', '.join([str(x).zfill(i + 1) for x in range(3)])}...", lambda render, i = i: str(render.line -1).zfill(i + 1)) for i in range(4)],
	*[(f"line{'0' * i}1", f"The item's line number in the format {', '.join([str(x + 1).zfill(i + 1) for x in range(3)])}...", lambda render, i = i: str(render.line).zfill(i + 1)) for i in range(4)],
	("voice", "The item's voice name as typed", lambda render: render.original_voice),
	("voice_lower", "The item's lowercase voice name as typed", lambda render: render.original_voice.lower()),
	("voice_slug", "The item's lowercased voice name with extraneous characters removed and spaces replaced with underscores", lambda render: slugify(render.original_voice.lower(), space_replacement = "_", char_passthroughs = ["_"])),
	("voice_aliased", "The item's voice name after alias replacement", lambda render: render.voice),
	("voice_lower_aliased", "The item's lowercase voice name after alias replacement", lambda render: render.voice.lower()),
	("voice_slug_aliased", "The item's lowercased voice name after alias replacement with extraneous characters removed and spaces replaced with underscores", lambda render: slugify(render.voice.lower(), space_replacement = "_", char_passthroughs = ["_"])),
	("text", "The item's text altered minimally to fit in a filename", lambda render: slugify(render.text[:200])),
	("text1", "The first word of the item's text", lambda render: slugify(" ".join(render.text[:200].split(" ")[:1]))),
	*[(f"text{i}", f"The item's first {i} words of text", lambda render, i = i: slugify(" ".join(render.text[:200].split(" ")[:i]))) for i in [2, 3, 5, 10, 15, 20]]
]

def render_filename_tokens_help():
	"""Returns a string that describes the usage of render filename template tokens, called when constructing the read only template help field in the star_client_configuration class."""
	return "\n".join([
		"It is possible to customize the output filenames produced by STAR with special tokens that are substituted with dynamic data.",
		"In the render filename template field, you can specify any of the following tokens by typing or pasting one between braces, for example {voice} or {text5}:"
	] + [f"\t{r[0]}: {r[1]}" for r in render_filename_tokens] + [""])

class render_filename:
	"""A small container class to store various properties about an item that is being rendered for the purposes of generating a valid custom filename, done this way so that render token lambdas have easy access to the data they need. Construct this object with valid arguments then access the filename property."""
	def __init__(self, counter, line, original_voice, voice, text, template = None):
		self.counter = counter
		self.line = line
		self.original_voice = original_voice
		self.voice = voice
		self.text = text
		self.template = config.get("render_filename_template", "{counter01}") if not template else template
	@property
	def filename(self):
		try: return self.template.format(**{r[0]: r[2](self) for r in render_filename_tokens})
		except Exception as e: return e

class voices_list(wx.ListCtrl):
	"""The voices list is implemented in virtual mode as it may contain a large number of items, this class facilitates that."""
	def OnGetItemText(self, item, column):
		if column == 0: return self.main_frame.voices[item]
	def update(self, main_frame):
		self.main_frame = main_frame
		self.SetItemCount(len(main_frame.voices))
		self.Refresh()

EVT_DONE_SPEAKING = wx.Window.NewControlId()
class done_speaking_event(wx.PyEvent):
	"""Miniaudio calls it's on stream end function on another thread, so we must implement our own WX event for the UI thread to be able to be notified when text finishes speaking."""
	def __init__(self, data = None):
		wx.PyEvent.__init__(self)
		self.SetEventType(EVT_DONE_SPEAKING)
		self.data = data

class star_client_configuration(wx.Dialog):
	"""This dialog is activated when the user clicks the options button in the main window."""
	def __init__(self, parent):
		"""Composes the UI elements for the dialog."""
		wx.Dialog.__init__(self, parent, title = "STAR Client Configuration")
		host_label = wx.StaticText(self, -1, "&Host to connect to")
		self.host = wx.TextCtrl(self, value = config.get("host", ""))
		self.host.SetHint("for example ws://username:password@server.com:7774")
		render_path_label = wx.StaticText(self, -1, "Default &Render location")
		self.render_path = wx.DirPickerCtrl(self, path = config.get("render_path", os.path.join(os.getcwd(), "output")), message = "Select a default directory to render output into")
		render_path_label.Reparent(self.render_path)
		wx.StaticText(self, -1, "Render &Filename template")
		self.render_filename_template = wx.TextCtrl(self, value = config.get("render_filename_template", "{counter01}"))
		wx.StaticText(self, -1, "Render Filename template tokens &information")
		wx.TextCtrl(self, style = wx.TE_MULTILINE | wx.HSCROLL | wx.TE_READONLY, value = render_filename_tokens_help())
		wx.StaticText(self, -1, "Amount of sil&ence (in milliseconds) to insert between consolidated speech clips")
		self.render_consolidated_silence = wx.SpinCtrl(self, value = config.get("render_consolidated_silence", "200"), max = 5000)
		wx.StaticText(self, -1, "Voice &preview text")
		self.voice_preview_text = wx.TextCtrl(self, value = config.get("voice_preview_text", "Hello there, my name is {voice}."))
		wx.StaticText(self, -1, "&Output Device")
		self.output_devices = wx.ListCtrl(self, style = wx.LC_SINGLE_SEL | wx.LC_REPORT)
		self.output_devices.AppendColumn("Device name")
		self.output_devices.Append(["Default"])
		for d in playsound_devices: self.output_devices.Append([d["name"]])
		device_idx = self.output_devices.FindItem(0, config.get("output_device", "Default"))
		self.output_devices.Focus(device_idx)
		self.output_devices.Select(device_idx)
		self.clear_output_on_render = wx.CheckBox(self, label = "Clear Output &subdirectory on render")
		self.clear_output_on_render.Value = config.as_bool("clear_output_on_render") if "clear_output_on_render" in config else True
		self.clear_cache_btn = wx.Button(self, label = "&Clear audio cache")
		self.clear_cache_btn.Bind(wx.EVT_BUTTON, self.on_clear_cache)
		self.clear_cache_btn.Enabled = hasattr(parent, "speech_cache") and len(parent.speech_cache) > 0
		self.CreateButtonSizer(wx.OK | wx.CANCEL)
		self.Bind(wx.EVT_INIT_DIALOG, self.on_show)
	def on_show(self, evt):
		device_idx = self.output_devices.FindItem(0, config.get("output_device", "Default"))
		self.output_devices.Focus(device_idx)
		self.output_devices.Select(device_idx)
		self.host.SetFocus()
	def on_clear_cache(self, evt):
		self.Parent.speech_cache = {}
		self.Parent.aliases_modified = True
		self.Parent.speech_requests_text = {}
		self.clear_cache_btn.Enabled = False
	async def validate_fail(self, parent, message, control):
		"""This not only makes the validate function below prettier, but it also serves as a minor hack that allows this dialog to run both before and after the WxAsync main loop has started."""
		dlg = wx.MessageDialog(self, message, "error")
		if parent == self: await AsyncShowDialogModal(dlg)
		else: dlg.ShowModal()
		control.SetFocus()
	async def validate(self, parent = None):
		if not parent: parent = self
		self.output_device = self.output_devices.GetItemText(self.output_devices.FocusedItem)
		render_fn = render_filename(1, 10, "Voice", "Text string", self.render_filename_template.Value).filename
		is_uri = is_valid_ws_uri(self.host.Value)
		preview_txt = ""
		try: self.voice_preview_text.Value.format(voice = "Voice")
		except Exception as e: preview_txt = e
		if type(is_uri) == str: await self.validate_fail(parent, f"host {is_uri}", self.host)
		elif not self.render_path.Path: await self.validate_fail(parent, "no render path provided", self.render_path)
		elif not self.render_filename_template.Value: await self.validate_fail(parent, "no render filename template provided", self.render_filename_template)
		elif type(render_fn) != str: await self.validate_fail(parent, f"Invalid render filename template {render_fn}", self.render_filename_template)
		elif not self.voice_preview_text.Value: await self.validate_fail(parent, "voice preview text must not be empty", self.voice_preview_text)
		elif type(preview_txt) != str: await self.validate_fail(parent, f"Invalid voice preview text {preview_txt}", self.voice_preview_text)
		else: return True
		return False

class star_client(wx.Frame):
	"""The main STAR client application."""
	def __init__(self, parent = None):
		"""The function that sets up and composes the app, from it's UI elements to the remote websocket connection."""
		wx.Frame.__init__(self, parent, title = "STAR Client")
		self.configuration = star_client_configuration(self)
		self.main_panel = wx.Panel(self)
		self.connecting_panel = wx.Panel(self)
		self.connecting_label = wx.StaticText(self.connecting_panel, -1, "Connecting..." if "host" in config else "Host not configured.")
		AsyncBind(wx.EVT_BUTTON, self.on_options, wx.Button(self.connecting_panel, label = "&Options"))
		wx.Button(self.connecting_panel, label = "&Exit").Bind(wx.EVT_BUTTON, self.on_exit_btn)
		sizer = wx.BoxSizer()
		voices_label = wx.StaticText(self.main_panel, -1, "&Voices")
		self.voices_list = voices_list(self.main_panel, style = wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
		AsyncBind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_preview_voice, self.voices_list)
		copy_voicename_id = wx.NewIdRef()
		self.voice_find_id = wx.NewIdRef()
		self.voice_find_next_id = wx.NewIdRef()
		self.voice_find_prev_id = wx.NewIdRef()
		self.Bind(wx.EVT_MENU, self.on_copy_voicename, id = copy_voicename_id)
		AsyncBind(wx.EVT_MENU, self.on_find_voice, self, id = self.voice_find_id)
		AsyncBind(wx.EVT_MENU, self.on_find_voice, self, id = self.voice_find_next_id)
		AsyncBind(wx.EVT_MENU, self.on_find_voice, self, id = self.voice_find_prev_id)
		self.voices_list.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('c'), copy_voicename_id), (wx.ACCEL_CTRL, ord("f"), self.voice_find_id), (wx.ACCEL_NORMAL, wx.WXK_F3, self.voice_find_next_id), (wx.ACCEL_SHIFT, wx.WXK_F3, self.voice_find_prev_id)]))
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
		self.script.Bind(wx.EVT_TEXT, self.on_script_change)
		render_title_label = wx.StaticText(self.main_panel, -1, "Output Sub&directory or consolidated filename")
		self.render_title = wx.TextCtrl(self.main_panel)
		self.render_btn = wx.Button(self.main_panel, label = "&Render to Disc")
		AsyncBind(wx.EVT_BUTTON, self.on_render, self.render_btn)
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
		sizer.Add(render_title_label, 0, wx.ALL, 5)
		sizer.Add(self.render_title, 0, wx.ALL, 5)
		sizer.Add(self.render_btn, 0, wx.ALL, 5)
		sizer.Add(options_btn, 0, wx.ALL, 5)
		sizer.Add(exit_btn, 0, wx.ALL, 5)
		self.main_panel.SetSizer(sizer)
		toggle_speaking_id = wx.NewIdRef()
		self.main_panel.Bind(wx.EVT_MENU, self.on_toggle_speaking, id = toggle_speaking_id)
		self.main_panel.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_ALT, wx.WXK_BACK, toggle_speaking_id)]))
		self.Connect(-1, -1, EVT_DONE_SPEAKING, self.on_auto_preview_next_script_line)
		self.main_panel.Hide()
		self.connecting_panel.Show()
		self.connecting_label.SetFocus()
		self.voices_list.InsertColumn(0, "voice name")
		self.voices = []
		self.voice_find_text = ""
		self.speech_requests = {}
		self.speech_requests_text = {}
		self.speech_cache = {}
		self.aliases = {}
		self.aliases_modified = False
		self.current_speech = None
		self.initial_connection = False
		self.websocket = None
		self.script_continuous_preview = False
		self.render_total = 0
		self.Show()
		self.connection_task = StartCoroutine(self.connect(config.get("host", "")), self)
	def on_copy_voicename(self, evt):
		"""Copies the currently focused voice name to the clipboard, called when ctrl+c is pressed on a voice name in the voices list."""
		voice = self.voices_list.FocusedItem
		if voice < 0 or voice >= len(self.voices):
			speech.speak("not focused on a voice")
			return
		if wx.TheClipboard.Open():
			wx.TheClipboard.SetData(wx.TextDataObject(self.voices[voice]))
			wx.TheClipboard.Close()
		speech.speak("copied")
	async def on_find_voice(self, evt):
		"""This handles ctrl+f, f3, and shift+f3 in the voices list."""
		if not self.voices:
			speech.speak("no voices to search")
			return
		dir = 1 if evt.Id != self.voice_find_prev_id else -1
		if evt.Id == self.voice_find_id or not self.voice_find_text:
			dlg = wx.TextEntryDialog(self, "search for", "Find", self.voice_find_text)
			r = await AsyncShowDialogModal(dlg)
			self.voices_list.SetFocus()
			if r == wx.ID_CANCEL: return
			self.voice_find_text = dlg.Value
		initial_idx = self.voices_list.FocusedItem
		idx = initial_idx + dir
		while idx != initial_idx:
			if dir < 0 and idx < 0: idx = len(self.voices) -1
			elif dir > 0 and idx >= len(self.voices): idx = 0
			if self.voice_find_text.lower() in self.voices[idx].lower(): break
			else: idx += dir
		if idx != initial_idx:
			self.voices_list.Select(idx)
			self.voices_list.Focus(idx);
		else: speech.speak("not found")
	async def on_preview_voice(self, evt):
		"""This is called when a voice in the voices list is activated, speaks a small sample of the voice."""
		self.script_continuous_preview = False
		await self.audiospeak(f"{evt.Label}: {config.get('voice_preview_text', 'Hello there, my name is {voice}.').format(voice = evt.Label)}")
	async def on_quickspeak(self, evt):
		"""Called when enter is pressed in the quickspeak text field, composes a simple speech request based on the current field value and speaks it."""
		voice = self.voices_list.FocusedItem
		if voice < 0 or voice >= len(self.voices):
			speech.speak("not focused on a voice")
			return
		if not self.quickspeak.Value:
			speech.speak("nothing to speak")
			return
		self.script_continuous_preview = False
		await self.audiospeak(f"{self.voices[voice]}: {self.quickspeak.Value.replace("\n", "  ")}")
	async def on_preview_script(self, evt):
		"""The script previewing facility, handles ctrl+alt+(space, up and down) calling self.audiospeak for each speech line detected."""
		pos = self.script.GetInsertionPoint()
		b, col, line = self.script.PositionToXY(pos)
		if evt.Id == self.preview_prev_id: line -= 1
		elif evt.Id == self.preview_next_id: line += 1
		if line < 0: line = 0
		line_len = self.script.GetLineLength(line)
		if line_len < 0: return
		new_pos = self.script.XYToPosition(0, line)
		if pos != new_pos: self.script.SetInsertionPoint(new_pos)
		self.script_continuous_preview = evt.Id == self.preview_continuous_id
		line_text = self.script.GetLineText(line).strip()
		if not line_text or line_text.startswith(";"):
			playsound("audio/metaline.ogg")
			return
		self.script_find_aliases()
		voice, params, line_text = parse_textline(line_text, self.aliases)
		if not voice or not line_text:
			playsound("audio/metaline.ogg", pitch = 0.8)
			return
		await self.audiospeak(f"{voice}{params}: {line_text}")
	def on_auto_preview_next_script_line(self, evt):
		"""This method gets called after a speech event has finished if the continuous script preview is active, it is responsible for scrolling to the next text line and previewing it."""
		voice = params = text = ""
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
			voice, params, text = parse_textline(text, self.aliases)
			if not voice or not text: continue
		StartCoroutine(self.audiospeak(f"{voice}{params}: {text}"), self)
	def on_script_change(self, evt):
		"""Called when the contents of the script field changes, indicates that we should rescan the field for aliases and metadata at next render or preview."""
		self.aliases_modified = True
	async def on_render(self, evt):
		"""The bulk of the rendering facility (called when Render to Disc is pressed), this method prepares renderable lines from the script and calls self.audiospeak for each event."""
		if self.render_total:
			await self.websocket.send(json.dumps({"user": USER_REVISION, "command": "abort"}))
			self.speech_requests = {}
			self.speech_requests_text = {}
			self.on_render_complete(True)
			return
		if getattr(self, "last_render", 0) > time.time() -1: return
		script = self.script.Value.strip()
		if not script: return await AsyncShowDialogModal(wx.MessageDialog(self, "You must provide a script for rendering", "error"))
		lines = script.split("\n")
		renderable_lines = []
		self.render_total = 1
		self.rendered_items = 0
		for i in range(len(lines)):
			l = lines[i].strip()
			if not l or l.startswith(";") or not ": " in l: continue
			orig_voice = parse_textline(l)[0]
			voice, params, text = parse_textline(l, self.aliases)
			if not voice or not text: continue
			render_fn = render_filename(self.render_total, i, orig_voice, voice, text).filename
			self.render_total += 1
			renderable_lines.append((render_fn, f"{voice}{params}: {text}"))
		if not renderable_lines:
			self.render_total = 0
			return await AsyncShowDialogModal(wx.MessageDialog(self, "no renderable data", "error"))
		self.last_render = time.time()
		self.script_find_aliases()
		playsound("audio/begin.ogg")
		self.render_path = self.render_output_path = os.path.join(config.get("render_path", os.path.join(os.getcwd(), "output")), self.render_title.Value)
		if os.path.splitext(self.render_title.Value)[1] in [".wav", ".mp3"]:
			self.render_output_path_tmp = tempfile.TemporaryDirectory()
			self.render_output_path = self.render_output_path_tmp.name
		if (not "clear_output_on_render" in config or config.as_bool("clear_output_on_render")) and self.render_title.Value:
			[os.remove(i) for i in glob.glob(os.path.join(config.get("render_path", os.path.join(os.getcwd(), "output")), self.render_title.Value, "*.wav"))]
		self.render_btn.Label = "Cancel"
		self.render_total = len(renderable_lines)
		for l in renderable_lines: await self.audiospeak(l[1], render_filename = l[0])
	def on_render_complete(self, canceled = False):
		"""This is called on completion or cancelation of a render, and handles any UI work involved in displaying this fact while preparing for a new render."""
		self.rendered_items = 0
		self.render_total = 0
		if not canceled:
			title = self.render_title.Value
			if os.path.splitext(title)[1] in [".wav", ".mp3"]:
				items = [i for i in glob.glob(os.path.join(self.render_output_path, "*.wav"))]
				combined = AudioSegment(data = b"", sample_width = 2, frame_rate = 44100, channels = 1)
				for i in items:
					if len(combined) > 0: combined += AudioSegment.silent(config.as_int("render_consolidated_silence") if "render_consolidated_silence" in config else 200)
					combined += AudioSegment.from_file(i)
				try: os.remove(self.render_path)
				except: pass
				output_basedir = os.path.split(self.render_path)[0]
				if not os.path.isdir(output_basedir): os.makedirs(output_basedir)
				combined.export(self.render_path, format = os.path.splitext(title)[1].lower()[1:], bitrate = "192k")
		if hasattr(self, "render_output_path_tmp"): del(self.render_output_path_tmp)
		self.render_btn.Label = "&Render to Disc"
		playsound("audio/complete.ogg" if not canceled else "audio/cancel.ogg")
	async def on_options(self, evt = None):
		"""Shows the options dialog and handles the saving of settings, either called as an event handler of the options button or else manually."""
		canceled = False
		while True:
			r = await AsyncShowDialogModal(self.configuration) if evt else self.configuration.ShowModal()
			if r != wx.ID_OK:
				canceled = True
				break
			if not await self.configuration.validate(None if evt else self): continue
			old_host = config.get("host", "")
			config["host"] = self.configuration.host.Value
			config["render_path"] = self.configuration.render_path.Path
			config["render_filename_template"] = self.configuration.render_filename_template.Value
			config["render_consolidated_silence"] = self.configuration.render_consolidated_silence.Value
			config["voice_preview_text"] = self.configuration.voice_preview_text.Value
			config["clear_output_on_render"] = self.configuration.clear_output_on_render.Value
			old_device = config.get("output_device", None)
			config["output_device"] = self.configuration.output_device
			if old_device != config["output_device"]: set_playsound_device(config["output_device"])
			if old_host != config["host"] and evt: self.reconnect()
			config.write()
			break
		if self.initial_connection: self.main_panel.SetFocus()
		else: self.connecting_panel.SetFocus()
		return not canceled
	def on_exit_btn(self, evt): self.Close()
	def on_toggle_speaking(self, evt):
		"""Called when the user presses alt+backspace, pauses or resumes any currently playing speech."""
		if not self.current_speech: return
		self.current_speech.pause() if self.current_speech.playing else self.current_speech.resume()
	def reconnect(self):
		"""Reestablishes the remote websocket connection, typically called if the host address is updated in the options dialog."""
		if self.connection_task: self.connection_task.cancel()
		self.initial_connection = False
		self.speech_requests = {}
		self.speech_requests_text = {}
		self.voices = {}
		self.voices_list.update(self)
		self.connecting_label.Label = "Connecting..."
		self.connecting_panel.Show()
		self.connecting_panel.SetFocus()
		self.connecting_label.SetFocus()
		self.main_panel.Hide()
		self.connection_task = StartCoroutine(self.connect(config.get("host", "")), self)
	async def connect(self, host):
		"""The bulk of the websocket handling logic, runs as an asynchronous task during the entire live state of a connection and calls into various helper methods such as on_connect, on_remote_binary, on_remote_message etc."""
		if not host: return
		if not await self.configuration.validate(self):
			r = await self.on_options()
			if not r: self.Close()
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
				await asyncio.sleep(3)
	async def on_connect(self, websocket):
		"""This function is fired on every successful websocket connection and is responsible for any UI modifications, server hello, and post-connection-setup required."""
		await websocket.send(json.dumps({"user": USER_REVISION}))
		self.websocket = websocket
		if not self.initial_connection:
			self.initial_connection = True
			self.connecting_panel.Hide()
			self.main_panel.Show()
			self.main_panel.SetFocus()
	def on_remote_binary(self, websocket, message):
		"""Handles any remote binary messages received from the server, mostly a jumping off point to self.on_remote_audio after some parsing."""
		if len(message) < 4: return
		id_len = int.from_bytes(message[:2], "little")
		id = message[2:id_len+2].partition(b"_")[2].partition(b"_")[0].decode()
		self.on_remote_audio(id, message[id_len+2:])
	def on_remote_message(self, websocket, message):
		"""Handles a parsed json payload received from the remote server."""
		if "voices" in message:
			playsound("audio/ready.ogg")
			diff = abs(len(message["voices"]) - len(self.voices))
			if len(message["voices"]) > len(self.voices):
				playsound("audio/voices_connect.ogg")
				if len(self.voices) > 0: speech.speak(f"{diff} {'voice' if diff == 1 else 'voices'} connected!")
			elif len(message["voices"]) < len(self.voices):
				playsound("audio/voices_disconnect.ogg")
				speech.speak(f"{diff} {'voice' if diff == 1 else 'voices'} disconnected.")
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
			self.speech_requests_text = {}
			if hasattr(self, "render_items"): self.render_items += 1
	def on_remote_audio(self, id, audio):
		"""Handles a remote audio payload, speaking it or saving it as a rendered item. Usually called from handle_remote_binary"""
		if not id in self.speech_requests: return # Rendering was likely canceled.
		r = self.speech_requests.pop(id)
		self.speech_cache[r.textline] = audio
		self.configuration.clear_cache_btn.Enabled = True
		if not r.render_filename:
			if self.current_speech: self.current_speech.close()
			self.current_speech = playsound(audio, finish_func = self.on_done_speaking)
		else: self.audiosave(r.render_filename, audio)
	def on_done_speaking(self, data):
		"""This gets called by the playsound class above when any currently playing speech has reached it's end. Importantly, it gets called on a thread controled by miniaudio so we need to post back to the main UI thread."""
		self.current_speech = None
		if self.script_continuous_preview: wx.PostEvent(self, done_speaking_event())
	def script_find_aliases(self):
		"""This searches through the script for metadata lines that begin with vertical bar (|) characters and attempts to parse voice aliases (|sam = Microsoft Sam) from such lines. It is called upon render or preview but is a no-op unless the script field has been modified since this method's last call."""
		if not self.aliases_modified: return
		self.aliases_modified = False
		self.aliases = {}
		line = -1
		while True:
			line += 1
			line_len = self.script.GetLineLength(line)
			if line_len < 0: return
			text = self.script.GetLineText(line).strip()
			if not text.startswith("|"): continue
			voice, sep, replacement = text[1:].partition("=")
			voice = voice.strip().lower()
			replacement = replacement.strip()
			if not voice or not replacement: continue
			self.aliases[voice] = replacement
	async def audiospeak(self, textline, render_filename = None):
		"""One of the main public interfaces in this application: Receives a parsable line of text "Sam: hello", and either plays the resulting speech synthesis or renders it if a sequence number is given."""
		if textline in self.speech_cache:
			if not render_filename:
				if self.current_speech: self.current_speech.close()
				self.current_speech = playsound(self.speech_cache[textline], finish_func = self.on_done_speaking)
				if textline in self.speech_requests_text: del(self.speech_requests_text[textline])
			else: self.audiosave(render_filename, self.speech_cache[textline])
		else:
			if not render_filename and textline in self.speech_requests_text and time.time() -self.speech_requests_text[textline] < 10:
				speech.speak("request in progress")
				return
			else: self.speech_requests_text[textline] = time.time()
			r = speech_request(textline, render_filename)
			self.speech_requests[r.request_id] = r
			await self.websocket.send(json.dumps({"user": USER_REVISION, "request": textline, "id": r.request_id}))
	def audiosave(self, filename, audio):
		"""Saves the contents of a bytes object (intended to be audio data) to the user's output directory, creating the output folder if necessary as well as handling some miscellaneous UI work related to rendering."""
		if not os.path.isdir(self.render_output_path): os.makedirs(self.render_output_path)
		with open(os.path.join(self.render_output_path, filename + ".wav"), "wb") as f: f.write(audio)
		self.rendered_items += 1
		if self.rendered_items < self.render_total: playsound("audio/progress.ogg", pitch = 0.6 + float(self.rendered_items / self.render_total))
		else: self.on_render_complete()

async def main():
	app = WxAsyncApp(sleep_duration = 0.001)
	client = star_client()
	await app.MainLoop()

if __name__ == "__main__": asyncio.run(main())
