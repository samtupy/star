# Originally provided by mad-gamer/ChatGPT, cleaned up and improved by Sam.
# pip install openai

import openai
import wx
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from provider import star_provider

class openaiplatform(star_provider):
	def get_voices(self):
		self.client = None
		voices = []
		for v in ["alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]:
			voices.append(v)
			if "hd_voices" in self.config and self.config.as_bool("hd_voices"): voices.append(v + " hd")
		return voices
	async def synthesize(self, voice, text, rate=None, pitch=None):
		model = "tts-1"
		if voice not in self.voices: return f"Error: Voice '{voice}' is not supported"
		if voice.endswith(" hd"):
			model += "-hd"
			voice = voice[:-3]
		if not self.client: self.client = openai.AsyncOpenAI(api_key = self.config.get("api_key", ""))
		kwargs = dict(model = model, voice = voice, input = text, response_format = "wav")
		if rate: kwargs["speed"] = rate
		return (await self.client.audio.speech.create(**kwargs)).content
	def add_configuration_options(self, panel):
		wx.StaticText(panel, -1, "OpenAI API &Key")
		panel.api_key = wx.TextCtrl(panel, value = self.config.get("api_key", ""))
		panel.hd_voices = wx.CheckBox(panel, label = "Include &HD Voices")
		panel.hd_voices.Value = "hd_voices" in self.config and self.config.as_bool("hd_voices")
	def write_configuration_options(self, panel, config):
		config["api_key"] = panel.api_key.Value
		config["hd_voices"] = panel.hd_voices.Value

if __name__ == "__main__": openaiplatform()
