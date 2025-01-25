# pip install google-cloud-texttospeech

import asyncio
import traceback
import wx
from google.cloud import texttospeech_v1
from provider import star_provider

class googlecloud(star_provider):
	async def get_voices(self):
		if not self.config.get("api_key", ""): return [] # Provider needs configuration
		self.client = texttospeech_v1.TextToSpeechAsyncClient(client_options = {"api_key": self.config["api_key"]})
		raw_voices = await self.client.list_voices()
		langs = self.config.get("language_codes", "en").split(" ")
		voices = {}
		for v in raw_voices.voices:
			langcode = ""
			for l1 in v.language_codes:
				for l2 in langs:
					if l1.startswith(l2):
						langcode = l1
						break
				if langcode: break
			if langcode: voices[v.name + " Google"] = {"full_name": v.name, "language_code": langcode}
		if hasattr(self, "do_configuration_interface"): self.client = None # Must destroy client object here to avoid unwanted delay and timeout warning on app exit.
		return voices
	async def synthesize(self, voice, text, rate = None, pitch = None):
		input = texttospeech_v1.SynthesisInput(text = text)
		vsp = texttospeech_v1.VoiceSelectionParams(language_code = self.voices[voice.replace("-", " ") + " Google"]["language_code"], name = voice)
		audio_config = texttospeech_v1.AudioConfig(audio_encoding = texttospeech_v1.types.AudioEncoding.LINEAR16)
		if rate: audio_config.speaking_rate = float(rate)
		if pitch: audio_config.pitch = float(pitch)
		try: result = await self.client.synthesize_speech(input = input, voice = vsp, audio_config = audio_config)
		except Exception as e:
			traceback.print_exc()
			return str(e)
		return result.audio_content
	def add_configuration_options(self, panel):
		wx.StaticText(panel, -1, "Google Cloud API &Key")
		panel.api_key = wx.TextCtrl(panel, value = self.config.get("api_key", ""))
		wx.StaticText(panel, -1, "Include &language codes with these prefixes (separated by spaces)")
		panel.language_codes = wx.TextCtrl(panel, value = self.config.get("language_codes", "en"))
	def write_configuration_options(self, panel, config):
		config["api_key"] = panel.api_key.Value

if __name__ == "__main__": googlecloud()
