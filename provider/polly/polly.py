# Original code provided by Ivan Soto before being minified and extended to add rate/pitch, multiple engines, mp3 output etc.
# To use, you'll need an AWS account and a configured AWS cli. Learn more at https://aws.amazon.com/polly/

import boto3
from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError
import traceback
import wx
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from provider import star_provider

class polly(star_provider):
	def __init__(self):
		self.language_codes = ["en-US", "en-GB", "en-IN", "en-AU", "en-GB-WLS", "en-NZ", "en-ZA", "en-IE"]
		self.engines = ["standard", "neural", "generative"]
		self.audio_cache = {}
		star_provider.__init__(self, synthesis_audio_extension = "mp3")
	def get_voices(self):
		self.polly = boto3.client('polly')
		raw_voices = []
		for l in self.language_codes:
			raw_voices += self.polly.describe_voices(LanguageCode = l).get("Voices", [])
		voices = {}
		for v in raw_voices:
			for engine in v["SupportedEngines"]:
				if not engine in self.engines: continue
				id = v["Id"] + " " + engine
				voices[id] = {"language": v["LanguageCode"]}
		return voices
	async def synthesize(self, voice, text, rate = None, pitch = None):
		cache_id = f"{voice} {text} {rate} {pitch}"
		if cache_id in self.audio_cache: return self.audio_cache[cache_id]
		voice_id, delim, voice_engine = voice.partition(" ")
		prosody = "<prosody " if (rate or pitch) else ""
		if rate:
			try: rate = str(float(rate)) + "%"
			except: pass
			prosody += f'rate="{rate}" '
		if pitch:
			try: pitch = str(float(pitch)) + "%"
			except: pass
			prosody += f'pitch="{pitch}" '
		if prosody: text = f"<speak>{prosody}>{text}</prosody></speak>"
		else: text = f"<speak>{text}</speak>"
		try: response = self.polly.synthesize_speech(Text = text, TextType = "ssml", Engine = voice_engine, VoiceId = voice_id, OutputFormat = "mp3", SampleRate = "24000")
		except (BotoCoreError, ClientError) as e: return str(e)
		if not "AudioStream" in response: return "response from amazon contains no audio stream! " + str(response)
		audio = response["AudioStream"].read()
		response["AudioStream"].close()
		self.audio_cache[cache_id] = audio
		return audio
	def add_configuration_options(self, panel):
		self.engine_options = {}
		for e in ["standard", "neural", "generative", "long-form"]:
			self.engine_options[e] = wx.CheckBox(panel, label = f"Enable &{e} voices")
			self.engine_options[e].Value = self.config.as_bool(f"engine_{e}") if f"engine_{e}" in self.config else e in ["standard", "neural"]
	def read_configuration_options(self):
		self.engines = []
		for e in ["standard", "neural", "generative", "long-form"]:
			if f"engine_{e}" in self.config and self.config.as_bool(f"engine_{e}"): self.engines.append(e)
	def write_configuration_options(self, panel, config):
		for e in ["standard", "neural", "generative", "long-form"]:
			config[f"engine_{e}"] = self.engine_options[e].Value

if __name__ == "__main__": polly()
