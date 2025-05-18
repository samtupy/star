import accessible_output2.outputs.auto
import atexit
import configobj
import ctypes
import glob
import json
import os
from pydub import AudioSegment
from smart_list import SmartList, Column, VirtualSmartList
from sound_lib.main import BassError
from sound_lib import output, stream
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import websockets.sync.client
import websockets.uri
import wx

USER_REVISION = 4

speech = accessible_output2.outputs.auto.Auto()
sound_output=output.Output(0)
config = configobj.ConfigObj(os.path.join(os.path.dirname(__file__), "STAR.ini"))

playsound_devices = sound_output.get_device_names()
playsound_device = playsound_devices.index(config.get("output_device", "Default"))
if playsound_device > -1: playsound_device += 1
sound_output.device = playsound_device
playing_sounds = []
class playsound:
	"""A wrapper class around sound_lib, created to make upgrading from a previously used miniaudio based system easier."""
	def __init__(self, data, finish_func = None, pitch = 1.0):
		if type(data) == bytes:
			self.data = ctypes.create_string_buffer(data)
			data = ctypes.addressof(self.data)
		self.handle = stream.FileStream(mem = type(data) != str, file = data, length = len(self.data) if type(data) != str else 0)
		if not self.handle: return
		self.handle.frequency *= pitch
		for s in playing_sounds:
			if not s.handle.is_playing and not s.handle.is_paused: playing_sounds.remove(s)
		self.handle.play()
		if finish_func:
			self.finish_func = finish_func
			threading.Thread(target = self.wait_for_finish, daemon = True).start()
		playing_sounds.append(self)
	def close(self):
		if not self.handle: return
		self.handle.free()
		self.handle = None
		if self in playing_sounds: playing_sounds.remove(self)
	def pause(self):
		return self.handle.pause() if self.handle else False
	def resume(self):
		return self.handle.play() if self.handle else False
	@property
	def playing(self): return self.handle.is_playing if self.handle else None
	def wait_for_finish(self):
		#Todo: Convert to bass sync when possible.
		try:
			while self.finish_func and self.handle and (self.handle.is_playing or self.handle.is_paused): time.sleep(0.005)
		except BassError: return
		if self.handle: self.finish_func(self)

def is_valid_ws_uri(uri):
	"""Helper function to insure a provided host is a valid websocket URI. Returns either True or an error string."""
	if not uri: return "must not be empty"
	try: websockets.uri.parse_uri(uri)
	except Exception as e: return str(e)
	return True;

def parse_textline(textline, aliases = {}):
	"""This utility function splits the provided line of script (Mike<r=2>: Hi there) into a tuple of voicename, params, text. Aliases is a dictionary of alias: full_voicename, and the returned voicename will be run through this replacement dictionary."""
	text = textline.partition(":")
	voicename = text[0].partition("<")
	params = "<" + voicename[2] if voicename[2] else ""
	voicename = voicename[0]
	if voicename.lower() in aliases: voicename = aliases[voicename.lower()]
	voicename, delim, default_params = voicename.partition("<")
	if default_params: default_params = "<" + default_params
	params = params if params else default_params
	return (voicename, params, text[2].strip())

def slugify(text, space_replacement = "", char_passthroughs = [" ", "_", "-", ",", ".", "!"]):
	"""Utility to convert a string into a valid filename."""
	if space_replacement: text = text.replace(" ", space_replacement)
	new_text = ""
	for char in text:
		if char.isalnum() or char in char_passthroughs: new_text += char
	return new_text

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
	*[(f"counter{'0' * (i + 1)}", f"A counter in the format {', '.join([str(x).zfill(i + 1) for x in range(3)])}...", lambda render, i = i: str(render.counter -1).zfill(i + 1)) for i in range(4)],
	*[(f"counter{'0' * i}1", f"A counter in the format {', '.join([str(x + 1).zfill(i + 1) for x in range(3)])}...", lambda render, i = i: str(render.counter).zfill(i + 1)) for i in range(4)],
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
	*[(f"text{i}", f"The item's first {i} words of text", lambda render, i = i: slugify(" ".join(render.text[:200].split(" ")[:i]))) for i in [2, 3, 5, 10, 15, 20]],
	("date", f"the date in the format {time.strftime('%Y-%m-%d')}", lambda render: time.strftime("%Y-%m-%d")),
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

EVT_DONE_SPEAKING = wx.Window.NewControlId()
class done_speaking_event(wx.PyEvent):
	"""Miniaudio calls it's on stream end function on another thread, so we must implement our own WX event for the UI thread to be able to be notified when text finishes speaking."""
	def __init__(self, data = None):
		wx.PyEvent.__init__(self)
		self.SetEventType(EVT_DONE_SPEAKING)
		self.data = data

EVT_REMOTE = wx.Window.NewControlId()
class remote_event(wx.PyEvent):
	"""We handle the websocket on another thread, this event posts any new messages from that thread to the main one."""
	def __init__(self, data = None):
		wx.PyEvent.__init__(self)
		self.SetEventType(EVT_REMOTE)
		self.data = data

class star_local:
	"""This class facilitates a convenient local STAR stack for cases when no remote servers are available. When the start method is called the coagulator and some providers are run, and when stop is called or the object is destroyed the child processes are terminated."""
	def __init__(self, client):
		self.client = client
		self.abort = threading.Event()
		self.processes = [["coagulator", [sys.executable, "../coagulator/coagulator.py", "--authless"] if not hasattr(sys, "frozen") else ["coagulator", "--authless"], None]]
		provider = "balcony" if sys.platform == "win32" else "macsay" if sys.platform == "darwin" else None
		if provider: self.processes.append([f"{provider} provider", [sys.executable, os.path.join("..", "provider", provider + ".py"), "--hosts", "ws://127.0.0.1:7774"] if not hasattr(sys, "frozen") else [provider, "--hosts", "ws://127.0.0.1:7774"], None])
		if sys.platform == "win32": self.processes.append(["sammy provider", [sys.executable, os.path.join("..", "provider", "sammy.py"), "--hosts", "ws://127.0.0.1:7774"] if not hasattr(sys, "frozen") else ["sammy", "--hosts", "ws://127.0.0.1:7774"], None])
	def __del__(self): self.stop()
	def start(self, silent = False):
		self.abort.clear()
		for p in self.processes:
			try: p[2] = subprocess.Popen(p[1], creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
			except Exception as e: return self.fail(f"Unable to start {p[0]}, {e}")
		threading.Thread(target = self.monitor, daemon = True).start()
		atexit.register(self.stop)
		return True
	def fail(self, message):
		wx.CallAfter(wx.MessageDialog(self.client, message, "Local STAR setup Error", wx.OK).ShowModal)
		wx.CallAfter(self.client.Close)
		self.stop()
		config["host"] = ""
		config.write() # insure the user doesn't get stuck in a loop of coagulation setup errors.
		return False
	def monitor(self):
		while not self.abort.wait(1):
			for p in self.processes:
				if p[2].poll() != None: p[2] = subprocess.Popen(p[1], creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
	def stop(self):
		self.abort.set()
		for p in self.processes:
			if p[2]: p[2].terminate()
			p[2] = None
		atexit.unregister(self.stop)

class star_client_configuration(wx.Dialog):
	"""This dialog is activated when the user clicks the options button in the main window."""
	def __init__(self, parent):
		"""Composes the UI elements for the dialog."""
		wx.Dialog.__init__(self, parent, title = "STAR Client Configuration")
		host_label = wx.StaticText(self, -1, "&Host to connect to")
		self.host = wx.ComboBox(self, value = config.get("host", ""))
		self.host.Bind(wx.EVT_COMBOBOX, self.on_host_selection_change)
		self.host.Bind(wx.EVT_TEXT, self.on_host_text_change)
		self.host.SetHint("for example ws://username:password@server.com:7774 or the string local")
		self.delete_host_btn = wx.Button(self, label = "&Delete saved host")
		self.delete_host_btn.Bind(wx.EVT_BUTTON, self.on_delete_saved_host)
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
		for d in playsound_devices: self.output_devices.Append([d])
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
		self.host.SetItems(config.get("previous_hosts", ["local"]))
		self.host.Value = config.get("host", "")
		self.host.SetFocus()
		self.delete_host_btn.Enabled = self.host.Value != "local" and self.host.FindString(self.host.Value) != wx.NOT_FOUND
	def on_clear_cache(self, evt):
		self.Parent.speech_cache = {}
		self.Parent.aliases_modified = True
		self.Parent.speech_requests_text = {}
		self.clear_cache_btn.Enabled = False
	def on_delete_saved_host(self, evt):
		sel = self.host.Selection if self.host.Selection != wx.NOT_FOUND else self.host.FindString(self.host.Value)
		if sel == wx.NOT_FOUND: return
		self.host.Delete(sel)
		self.host.Selection = 0
		self.delete_host_btn.Enabled = self.host.Selection != -1 and self.host.Value != "local"
		self.host.SetFocus()
	def on_host_selection_change(self, evt):
		self.delete_host_btn.Enabled = self.host.Selection != -1 and self.host.Value != "local"
	def on_host_text_change(self, evt):
		self.delete_host_btn.Enabled = self.host.Value != "local" and self.host.FindString(self.host.Value) != -1
	def validate_fail(self, message, control):
		"""This is just a small utility that shows a message and focuses a control, used for showing options validation failures."""
		dlg = wx.MessageDialog(self, message, "error")
		dlg.ShowModal()
		control.SetFocus()
	def validate(self):
		"""Insures that values entered into the options dialog are sane, showing error dialogs if not and returning a boolean value in either case (True for validated settings)."""
		self.output_device = self.output_devices.GetItemText(self.output_devices.FocusedItem)
		render_fn = render_filename(1, 10, "Voice Orig", "Voice", "Text string", self.render_filename_template.Value).filename
		is_uri = self.host.Value == "local" or is_valid_ws_uri(self.host.Value)
		preview_txt = ""
		try: self.voice_preview_text.Value.format(voice = "Voice")
		except Exception as e: preview_txt = e
		if type(is_uri) == str: self.validate_fail(f"host {is_uri}", self.host)
		elif not self.render_path.Path: self.validate_fail("no render path provided", self.render_path)
		elif not self.render_filename_template.Value: self.validate_fail("no render filename template provided", self.render_filename_template)
		elif type(render_fn) != str: self.validate_fail(f"Invalid render filename template {render_fn}", self.render_filename_template)
		elif not self.voice_preview_text.Value: self.validate_fail("voice preview text must not be empty", self.voice_preview_text)
		elif type(preview_txt) != str: self.validate_fail(f"Invalid voice preview text {preview_txt}", self.voice_preview_text)
		else: return True
		return False

class star_client(wx.Frame):
	"""The main STAR client application."""
	def __init__(self, parent = None):
		"""The function that sets up and composes the app, from it's UI elements to the remote websocket connection."""
		wx.Frame.__init__(self, parent, title = "STAR Client", size = (1024, 1024))
		self.configuration = star_client_configuration(self)
		self.main_panel = wx.Panel(self)
		self.connecting_panel = wx.Panel(self)
		self.connecting_label = wx.StaticText(self.connecting_panel, -1, "Connecting..." if "host" in config and config["host"] != "" else "Host not configured.")
		self.run_local_btn = wx.Button(self.connecting_panel, label = "Run &locally")
		self.run_local_btn.Bind(wx.EVT_BUTTON, self.on_run_local)
		self.run_local_btn.Enabled = config.get("host", "") != "local"
		wx.Button(self.connecting_panel, label = "&Options").Bind(wx.EVT_BUTTON, self.on_options)
		wx.Button(self.connecting_panel, label = "&Exit").Bind(wx.EVT_BUTTON, self.on_exit_btn)
		self.main_sizer = wx.BoxSizer(wx.VERTICAL)
		wx.StaticText(self.main_panel, -1, "&Voices")
		self.voices_list = VirtualSmartList(parent = self.main_panel, style = wx.LC_REPORT | wx.LC_SINGLE_SEL, get_virtual_item = lambda v: self.voices[v], update_cache = lambda v_from, v_to: self.voices[v_from:v_to + 1])
		self.voices_list.SetLabel("Voices")
		self.voices_list.set_columns([Column(title = "voice name", model_field = "name", width = 300)])
		self.voices_list.control.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_preview_voice)
		copy_voicename_id = wx.NewIdRef()
		self.voice_find_id = wx.NewIdRef()
		self.voice_find_next_id = wx.NewIdRef()
		self.voice_find_prev_id = wx.NewIdRef()
		self.Bind(wx.EVT_MENU, self.on_copy_voicename, id = copy_voicename_id)
		self.Bind(wx.EVT_MENU, self.on_find_voice, id = self.voice_find_id)
		self.Bind(wx.EVT_MENU, self.on_find_voice, id = self.voice_find_next_id)
		self.Bind(wx.EVT_MENU, self.on_find_voice, id = self.voice_find_prev_id)
		self.voices_list.control.control.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('c'), copy_voicename_id), (wx.ACCEL_CTRL, ord("f"), self.voice_find_id), (wx.ACCEL_NORMAL, wx.WXK_F3, self.voice_find_next_id), (wx.ACCEL_SHIFT, wx.WXK_F3, self.voice_find_prev_id)]))
		self.quickspeak, quickspeak_label = self.create_labeled_control("&Quickspeak", wx.TextCtrl, self.main_panel, style = wx.TE_PROCESS_ENTER | wx.TE_MULTILINE | wx.HSCROLL)
		self.quickspeak.Bind(wx.EVT_TEXT_ENTER, self.on_quickspeak)
		self.script, script_label = self.create_labeled_control("Enter &Script", wx.TextCtrl, self.main_panel, size = (768, 512), style = wx.TE_MULTILINE | wx.TE_RICH2 | wx.HSCROLL)
		self.preview_prev_id = wx.NewIdRef()
		self.preview_next_id = wx.NewIdRef()
		self.preview_cur_id = wx.NewIdRef()
		self.preview_continuous_id = wx.NewIdRef()
		self.Bind(wx.EVT_MENU, self.on_preview_script, id = self.preview_prev_id)
		self.Bind(wx.EVT_MENU, self.on_preview_script, id = self.preview_next_id)
		self.Bind(wx.EVT_MENU, self.on_preview_script, id = self.preview_cur_id)
		self.Bind(wx.EVT_MENU, self.on_preview_script, id = self.preview_continuous_id)
		self.script.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CTRL | wx.ACCEL_ALT, ord(' '), self.preview_cur_id), (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_UP, self.preview_prev_id), (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_DOWN, self.preview_next_id), (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_RETURN, self.preview_continuous_id)]))
		self.script.Bind(wx.EVT_TEXT, self.on_script_change)
		self.render_title, render_title_label = self.create_labeled_control("Output Sub&directory or consolidated filename", wx.TextCtrl, self.main_panel)
		self.render_btn = wx.Button(self.main_panel, label = "&Render to Disc")
		self.render_btn.Bind(wx.EVT_BUTTON, self.on_render)
		self.render_progress = wx.Gauge(self.main_panel, range = 100)
		self.render_progress.Hide()
		options_btn = wx.Button(self.main_panel, label = "&Options")
		options_btn.Bind(wx.EVT_BUTTON, self.on_options)
		exit_btn = wx.Button(self.main_panel, id = wx.NewIdRef(), label = "E&xit")
		exit_btn.Bind(wx.EVT_BUTTON, self.on_exit_btn)
		self.main_sizer.Add(self.render_btn, 3, wx.ALL | wx.EXPAND, 5)
		self.main_sizer.Add(self.render_progress, 3, wx.ALL | wx.EXPAND, 5)
		self.main_sizer.Add(options_btn, 3, wx.ALL | wx.EXPAND, 5)
		self.main_sizer.Add(exit_btn, 3, wx.ALL | wx.EXPAND, 5)
		self.main_sizer.SetSizeHints(self.main_panel)
		self.main_panel.SetSizer(self.main_sizer)
		toggle_speaking_id = wx.NewIdRef()
		self.main_panel.Bind(wx.EVT_MENU, self.on_toggle_speaking, id = toggle_speaking_id)
		self.main_panel.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_ALT, wx.WXK_BACK, toggle_speaking_id), (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, exit_btn.Id)]))
		self.connecting_panel.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_ALT, wx.WXK_BACK, toggle_speaking_id), (wx.ACCEL_NORMAL, wx.WXK_ESCAPE, exit_btn.Id)]))
		self.Connect(-1, -1, EVT_REMOTE, self.on_remote_event)
		self.Connect(-1, -1, EVT_DONE_SPEAKING, self.on_auto_preview_next_script_line)
		self.Bind(wx.EVT_CLOSE, self.on_exit)
		self.main_panel.Hide()
		self.connecting_panel.Layout()
		self.connecting_panel.Show()
		self.connecting_label.SetFocus()
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
		self.last_renderable_lines = []
		self.Show()
		self.Centre()
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.connecting_panel, 1, wx.EXPAND)
		sizer.Add(self.main_panel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.connection_abort = threading.Event()
		if "host" in config and config["host"] != "" and not self.configuration.validate():
			r = self.on_options()
			if not r: return wx.Exit()
		if self.check_local():
			self.connection_thread = threading.Thread(target = self.connect, args = [config.get("host", "") if not self.local else "ws://127.0.0.1:7774"], daemon = True)
			self.connection_thread.start()
		else: self.connection_thread = None
	def create_labeled_control(self, label, control_class, *args, **kwargs):
		"""Helper function that creates static label text for a control, then returns a two item tuple with the control argument as passed followed by the wx.StaticText object created for the label."""
		label_object = wx.StaticText(self.main_panel, -1, label)
		self.main_sizer.Add(label_object, 1, wx.EXPAND | wx.ALL, 1)
		control = control_class(*args, **kwargs)
		self.main_sizer.Add(control, 3, wx.EXPAND | wx.BOTTOM, 10)
		return (control, label_object)
	def check_local(self):
		"""If the host is 'local', set up a star_local object. Otherwise, destroy it thus terminating the child coagulator and providers. Returns false if the connection thread should not be started because the local stack failed to be set up."""
		if config.get("host", "") == "local":
			self.local = star_local(self)
			if not self.local.start():
				self.local = None
				return False
		else:
			if hasattr(self, "local") and self.local: self.local.stop()
			self.local = None
		self.run_local_btn.Enabled = config.get("host", "") != "local"
		return True
	def on_copy_voicename(self, evt):
		"""Copies the currently focused voice name to the clipboard, called when ctrl+c is pressed on a voice name in the voices list."""
		voice = self.voices_list.get_selected_index()
		if voice < 0 or voice >= len(self.voices):
			speech.speak("not focused on a voice")
			return
		if wx.TheClipboard.Open():
			wx.TheClipboard.SetData(wx.TextDataObject(self.voices[voice]["name"]))
			wx.TheClipboard.Close()
		speech.speak("copied")
	def on_find_voice(self, evt):
		"""This handles ctrl+f, f3, and shift+f3 in the voices list."""
		if not self.voices:
			speech.speak("no voices to search")
			return
		dir = 1 if evt.Id != self.voice_find_prev_id else -1
		if evt.Id == self.voice_find_id or not self.voice_find_text:
			dlg = wx.TextEntryDialog(self, "search for", "Find", self.voice_find_text)
			r = dlg.ShowModal()
			self.voices_list.control.control.SetFocus()
			if r == wx.ID_CANCEL: return
			self.voice_find_text = dlg.Value
		initial_idx = self.voices_list.get_selected_index()
		idx = initial_idx + dir
		while True:
			if dir < 0 and idx < 0: idx = len(self.voices) -1
			elif dir > 0 and idx >= len(self.voices): idx = 0
			if idx == initial_idx or self.voice_find_text.lower() in self.voices[idx]["name"].lower(): break
			else: idx += dir
		if idx != initial_idx:
			self.voices_list.set_selected_index(idx)
		else: speech.speak("not found")
	def on_preview_voice(self, evt):
		"""This is called when a voice in the voices list is activated, speaks a small sample of the voice."""
		self.script_continuous_preview = False
		voice = self.voices_list.get_selected_index()
		if voice < 0: return
		voice = self.voices[voice]["name"]
		self.audiospeak(f"{voice}: {config.get('voice_preview_text', 'Hello there, my name is {voice}.').format(voice = voice)}")
	def on_quickspeak(self, evt):
		"""Called when enter is pressed in the quickspeak text field, composes a simple speech request based on the current field value and speaks it."""
		voice = self.voices_list.get_selected_index()
		if voice < 0 or voice >= len(self.voices):
			speech.speak("not focused on a voice")
			return
		if not self.quickspeak.Value:
			speech.speak("nothing to speak")
			return
		self.script_continuous_preview = False
		text_to_quickspeak = self.quickspeak.Value.replace('\n', '  ')
		self.audiospeak(f"{self.voices[voice]['name']}: {text_to_quickspeak}")
	def on_preview_script(self, evt):
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
		self.audiospeak(f"{voice}{params}: {line_text}")
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
		self.audiospeak(f"{voice}{params}: {text}")
	def on_script_change(self, evt):
		"""Called when the contents of the script field changes, indicates that we should rescan the field for aliases and metadata at next render or preview."""
		self.aliases_modified = True
	def on_render(self, evt):
		"""The bulk of the rendering facility (called when Render to Disc is pressed), this method prepares renderable lines from the script and calls self.audiospeak for each event."""
		if self.render_total:
			self.websocket.send(json.dumps({"user": USER_REVISION, "command": "abort"}))
			self.speech_requests = {}
			self.speech_requests_text = {}
			self.on_render_complete(True)
			return
		if getattr(self, "last_render", 0) > time.time() -1: return
		script = self.script.Value.strip()
		if not script: return wx.MessageDialog(self, "You must provide a script for rendering", "error").ShowModal()
		self.script_find_aliases()
		lines = script.split("\n")
		renderable_lines = []
		selected_renderable_lines = []
		selection_block_depth = 0
		self.render_total = 1
		self.rendered_items = 0
		for i in range(len(lines)):
			l = lines[i].strip()
			if l == "<" or l == ">":
				selection_block_depth += (1 if l == "<" else -1)
				continue
			if not l or l.startswith(";") or not ": " in l: continue
			orig_voice = parse_textline(l)[0]
			voice, params, text = parse_textline(l, self.aliases)
			if not voice or not text: continue
			render_fn = render_filename(self.render_total, i, orig_voice, voice, text).filename
			self.render_total += 1
			rl = (render_fn, f"{voice}{params}: {text}")
			renderable_lines.append(rl)
			if selection_block_depth > 0: selected_renderable_lines.append(rl)
		if selection_block_depth:
			self.render_total = 0
			return wx.MessageDialog(self, "unmatched render block selection tokens <> level " + str(selection_block_depth), "error").ShowModal()
		if not renderable_lines:
			self.render_total = 0
			return wx.MessageDialog(self, "no renderable data", "error").ShowModal()
		self.last_render = time.time()
		playsound("audio/begin.ogg")
		self.render_path = self.render_output_path = os.path.join(config.get("render_path", os.path.join(os.getcwd(), "output")), self.render_title.Value)
		if os.path.splitext(self.render_title.Value)[1] in [".wav", ".mp3"]:
			self.render_output_path_tmp = tempfile.TemporaryDirectory()
			self.render_output_path = self.render_output_path_tmp.name
		if (not "clear_output_on_render" in config or config.as_bool("clear_output_on_render")) and self.render_title.Value:
			[os.remove(i) for i in glob.glob(os.path.join(config.get("render_path", os.path.join(os.getcwd(), "output")), self.render_title.Value, "*.*"))]
		self.render_btn.Label = "Cancel"
		if selected_renderable_lines: renderable_lines = selected_renderable_lines
		self.render_total = len(renderable_lines)
		self.render_progress.Range = self.render_total
		self.render_progress.Value = 0
		self.render_progress.Show()
		self.last_renderable_lines = renderable_lines
		for l in renderable_lines:
			if not self.render_total: return # render canceled
			self.audiospeak(l[1], render_filename = l[0])
	def on_render_complete(self, canceled = False):
		"""This is called on completion or cancelation of a render, and handles any UI work involved in displaying this fact while preparing for a new render."""
		del(self.rendered_items)
		self.render_total = 0
		if not canceled:
			title = self.render_title.Value
			if os.path.splitext(title)[1] in [".wav", ".mp3"]:
				items = [os.path.join(self.render_output_path, i[0] + "." + self.speech_cache[i[1]]["extension"]) for i in self.last_renderable_lines]
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
		self.render_progress.Hide()
	def on_run_local(self, evt):
		"""If this button is clicked from the connection panel, spin up a local STAR stack and initiate a connection to it."""
		if self.local: return wx.MessageDialog(self, "Already attempting to establish local setup", "error", wx.OK)
		config["host"] = "local"
		config.write()
		self.reconnect()
	def on_options(self, evt = None):
		"""Shows the options dialog and handles the saving of settings, either called as an event handler of the options button or else manually."""
		canceled = False
		while True:
			r = self.configuration.ShowModal()
			if r != wx.ID_OK:
				canceled = True
				break
			if not self.configuration.validate(): continue
			old_host = config.get("host", "")
			config["host"] = self.configuration.host.Value
			config["previous_hosts"] = self.configuration.host.GetItems()
			if not config["host"] in config["previous_hosts"]:
				config["previous_hosts"].insert(0, config["host"])
				self.configuration.host.Insert(config["host"], 0)
			config["render_path"] = self.configuration.render_path.Path
			config["render_filename_template"] = self.configuration.render_filename_template.Value
			config["render_consolidated_silence"] = self.configuration.render_consolidated_silence.Value
			config["voice_preview_text"] = self.configuration.voice_preview_text.Value
			config["clear_output_on_render"] = self.configuration.clear_output_on_render.Value
			old_device = config.get("output_device", None)
			config["output_device"] = self.configuration.output_device
			if old_device != config["output_device"]: sound_output.device = playsound_devices.index(config["output_device"]) + 1
			if old_host != config["host"] and evt: self.reconnect()
			config.write()
			break
		if self.initial_connection: self.main_panel.SetFocus()
		else: self.connecting_panel.SetFocus()
		return not canceled
	def on_exit_btn(self, evt):
		self.Close()
		wx.Exit()
	def on_exit(self, evt):
		"""This is called when the main window is closing, and allows us to do some cleanup."""
		self.Hide()
		if self.websocket: self.websocket.close()
		if self.local: self.local.stop()
		self.local = None
		self.connection_abort.set()
		evt.Skip()
	def on_toggle_speaking(self, evt):
		"""Called when the user presses alt+backspace, pauses or resumes any currently playing speech."""
		if not self.current_speech: return
		self.current_speech.pause() if self.current_speech.playing else self.current_speech.resume()
	def reconnect(self, label = "Connecting...", full = True):
		"""Reestablishes the remote websocket connection, typically called if the host address is updated in the options dialog. If full is set to False, only the UI will be updated while the connection thread and socket are left in tact."""
		if full and self.websocket: self.websocket.close()
		if full and self.connection_thread:
			self.connection_abort.set()
			self.connection_thread.join()
			self.connection_thread = None
		self.initial_connection = False
		self.speech_requests = {}
		self.speech_requests_text = {}
		self.voices = []
		self.voices_list.update_count(len(self.voices))
		label_change = self.connecting_label.Label != label
		self.connecting_label.Label = label
		self.connecting_panel.Show()
		if label_change: self.connecting_label.SetFocus()
		self.main_panel.Hide()
		if full and self.check_local():
			self.connection_thread = threading.Thread(target = self.connect, args = [config.get("host", "") if not self.local else "ws://127.0.0.1:7774"], daemon = True)
			self.connection_thread.start()
	def connect(self, host):
		"""The bulk of the websocket handling logic, runs as an extra thread during the entire live state of a connection which post our custom wx EVT_REMOTE events which will in turn call into various helper methods such as on_connect, on_remote_binary, on_remote_message etc."""
		self.connection_abort.clear()
		if not host: return
		should_exit = False
		while not should_exit and not self.connection_abort.wait(0.005):
			try:
				with websockets.sync.client.connect(host, max_size = None, max_queue = 4096) as websocket:
					wx.PostEvent(self, remote_event({"connect": websocket}))
					while not self.connection_abort.wait(0.005):
						try: message = websocket.recv(30)
						except TimeoutError:
							websocket.ping()
							continue
						if type(message) == bytes:
							wx.PostEvent(self, remote_event({"binary": message, "websocket": websocket}))
						else:
							try:
								event = json.loads(message)
								wx.PostEvent(self, remote_event({"message": event, "websocket": websocket}))
							except json.JSONDecodeError:
								print("Received an invalid JSON message:", message)
			except websockets.exceptions.ConnectionClosedOK: continue
			except websockets.exceptions.InvalidURI as e: return wx.PostEvent(self, remote_event({"fail": str(e)}))
			except websockets.exceptions.InvalidStatus as e: return wx.PostEvent(self, remote_event({"fail": f"{e} {e.response.reason_phrase};	 {e.response.body.decode().strip()}"}))
			except Exception as e:
				traceback.print_exc()
				wx.PostEvent(self, remote_event({"fail": f"Reconnecting... {e}", "refocus": False}))
				if self.connection_abort.wait(3): return
	def on_remote_event(self, evt):
		"""Events received by the websocket thread are passed to this function where we can then finally invoque various helper methods that might touch the UI such as on_connect and friends."""
		evt = evt.data
		if "connect" in evt: self.on_connect(evt["connect"])
		elif "fail" in evt:
			if self.connecting_label.Label != evt["fail"]: playsound("audio/error.ogg")
			self.reconnect(evt["fail"], False)
		elif "binary" in evt: self.on_remote_binary(evt["websocket"], evt["binary"])
		elif "message" in evt: self.on_remote_message(evt["websocket"], evt["message"])
	def on_connect(self, websocket):
		"""This function is fired on every successful websocket connection and is responsible for any UI modifications, server hello, and post-connection-setup required."""
		websocket.send(json.dumps({"user": USER_REVISION}))
		self.websocket = websocket
		if not self.initial_connection:
			self.initial_connection = True
			self.connecting_panel.Hide()
			self.connecting_label.Label = "Connecting..."
			self.main_panel.Show()
			self.Layout()
			self.main_panel.SetFocus()
	def on_remote_binary(self, websocket, message):
		"""Handles any remote binary messages received from the server, mostly a jumping off point to self.on_remote_audio after some parsing."""
		if len(message) < 4: return
		meta_len = int.from_bytes(message[:2], "little")
		meta = message[2:meta_len+2].decode()
		if meta.startswith("{"): meta = json.loads(meta)
		else: meta = {"id": meta}
		if not "id" in meta: return
		meta["id"] = meta["id"].partition("_")[2].partition("_")[0]
		self.on_remote_audio(meta, message[meta_len+2:])
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
			focused_voice = self.voices_list.get_selected_index()
			if focused_voice > -1 and focused_voice < len(self.voices): focused_voice = self.voices[focused_voice]
			else: focused_voice = 0
			self.voices = message["voices"]
			# compat; try to remove by v6.
			if len(self.voices) > 0 and type(self.voices[0]) == str: self.voices = [{"name": v} for v in self.voices]
			self.voices_list.update_count(len(self.voices))
			if type(focused_voice) == dict:
				try: focused_voice = self.voices_list.find_index_of_item(focused_voice)
				except ValueError: focused_voice = -1
			if len(self.voices) > 0 and focused_voice > -1 and self.voices_list.get_selected_index() != focused_voice: self.voices_list.set_selected_index(focused_voice)
		elif "error" in message:
			playsound("audio/error.ogg")
			speech.speak(message["error"])
		elif "status" in message:
			playsound("audio/warning.ogg")
			speech.speak(message["status"])
			self.speech_requests_text = {}
			if "abort" in message and message["abort"] and hasattr(self, "rendered_items"): self.audiosave(None, None)
		elif "warning" in message:
			playsound("audio/warning.ogg")
			speech.speak(message["warning"])
			self.speech_requests_text = {}
			if hasattr(self, "rendered_items"): self.audiosave(None, None)
	def on_remote_audio(self, meta, audio):
		"""Handles a remote audio payload, speaking it or saving it as a rendered item. Usually called from on_remote_binary. The meta dictionnary is expected to contain at least an id member."""
		id = meta["id"]
		ext = meta.get("extension", "wav")
		if not id in self.speech_requests: return # Rendering was likely canceled.
		r = self.speech_requests.pop(id)
		self.speech_cache[r.textline] = {"audio": audio, "extension": ext}
		self.configuration.clear_cache_btn.Enabled = True
		if not r.render_filename:
			if self.current_speech: self.current_speech.close()
			self.current_speech = playsound(audio, finish_func = self.on_done_speaking)
		else: self.audiosave(f"{r.render_filename}.{ext}", audio)
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
	def audiospeak(self, textline, render_filename = None):
		"""One of the main public interfaces in this application: Receives a parsable line of text "Sam: hello", and either plays the resulting speech synthesis or renders it if a sequence number is given."""
		if textline in self.speech_cache:
			if not render_filename:
				if self.current_speech: self.current_speech.close()
				self.current_speech = playsound(self.speech_cache[textline]["audio"], finish_func = self.on_done_speaking)
				if textline in self.speech_requests_text: del(self.speech_requests_text[textline])
			else: self.audiosave(render_filename + "." + self.speech_cache[textline]["extension"], self.speech_cache[textline]["audio"])
		else:
			if not render_filename and textline in self.speech_requests_text and time.time() -self.speech_requests_text[textline] < 10:
				speech.speak("request in progress")
				return
			else: self.speech_requests_text[textline] = time.time()
			r = speech_request(textline, render_filename)
			self.speech_requests[r.request_id] = r
			self.websocket.send(json.dumps({"user": USER_REVISION, "request": textline, "id": r.request_id}))
	def audiosave(self, filename, audio):
		"""Saves the contents of a bytes object (intended to be audio data) to the user's output directory, creating the output folder if necessary as well as handling some miscellaneous UI work related to rendering. If filename or audio is not provided, the UI is updated standalone (used for things like render warnings that still need to increase the progress bar)."""
		if filename and audio:
			if not os.path.isdir(self.render_output_path): os.makedirs(self.render_output_path)
			with open(os.path.join(self.render_output_path, filename), "wb") as f: f.write(audio)
			wx.Yield()
		self.rendered_items += 1
		self.render_progress.Value = self.rendered_items
		wx.Yield()
		if self.rendered_items >= self.render_total: self.on_render_complete()

def main():
	os.chdir(os.path.dirname(__file__))
	app = wx.App()
	client = star_client()
	app.MainLoop()

if __name__ == "__main__": main()
