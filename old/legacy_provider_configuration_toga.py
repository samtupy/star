# This is a record of the provider configuration code that used to be used when I was trying to employ Toga as a UI library, we've since switched to WxPython.

class star_provider_configurator(toga.App):
	"""This is a small Toga app that allows one to configure the provider with a list of hosts to connect to, and any other future options."""
	def __init__(self, provider):
		self.provider = provider
		toga.App.__init__(self, "STAR provider configuration", "com.samtupy.STARProvider")
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

