# pip install elevenlabs
import traceback
import wx
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from provider import star_provider
from elevenlabs.client import ElevenLabs, AsyncElevenLabs
from elevenlabs import VoiceSettings

class eleven(star_provider):
	def __init__(self):
		self.client = None
		super().__init__(synthesis_audio_extension="mp3")

	def get_voices(self):
		try:
			cl = ElevenLabs(api_key=self.config.get("api_key", ""))
			voices_resp = cl.voices.get_all().voices
		except Exception:
			traceback.print_exc()
			return {}
		voices = {}
		for v in voices_resp:
			key = f"{v.name}-eleven"
			voices[key] = {"full_name": v.voice_id}
		return voices

	async def synthesize(self, voice: str, text: str, rate: float = None, pitch=None):
		if self.client is None:
			api_key = self.config.get("api_key", "")
			if not api_key:
				raise ValueError("API key is missing.")
			self.client = AsyncElevenLabs(api_key=api_key)

		try:
			audio_iter = self.client.text_to_speech.convert(
				voice_id=voice,
				text=text,
				model_id="eleven_multilingual_v2",
				voice_settings=VoiceSettings(
					stability=(0.75 if rate is None else rate),
					similarity_boost=0.5,
					style=0.0
				)
			)
			if audio_iter is None:
				raise RuntimeError("TTS generation failed: no audio stream returned.")

			audio = b""
			async for chunk in audio_iter:
				if isinstance(chunk, bytes):
					audio += chunk

			return audio

		except Exception:
			traceback.print_exc()
			return None

	def add_configuration_options(self, panel):
		wx.StaticText(panel, -1, "Eleven Labs API Key")
		panel.api_key = wx.TextCtrl(panel, value=self.config.get("api_key", ""))

	def write_configuration_options(self, panel, config):
		config["api_key"] = panel.api_key.Value

if __name__ == "__main__":
	eleven()