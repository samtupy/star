from provider import star_provider
from elevenlabs.client import AsyncElevenLabs
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice as eleven_voice, VoiceSettings
import typing
class eleven(star_provider):
	def __init__(self):
		self.client = None
		star_provider.__init__(self, synthesis_audio_extension = "mp3")
	def get_voices(self):
		cl= ElevenLabs(api_key = self.config.get("api_key", ""))
		result = cl.voices.get_all().voices
		voices = {}
		for v in result:
			key = v.name+"-eleven"
			voices[key]= {"full_name": v.voice_id}
		return voices
	async def synthesize(self, voice, text, rate=None, pitch=None):
		if self.client is None:
			api_key = self.config.get("api_key", "")
			if not api_key:
				raise ValueError("API key is missing.")
			self.client = AsyncElevenLabs(api_key=api_key)
		try:
			result = await self.client.generate(
				text=text,
				voice=eleven_voice(voice_id = voice, settings = VoiceSettings(stability = (0.75 if rate is None else rate), similarity_boost = 0.5, style = 0.0)),
				stream=False #this is currently broken, it seems.
			)
			if isinstance(result, typing.AsyncGenerator):
				audio = b""
				async for chunk in result:
					audio += chunk
				return audio
			else:
				return result
		except Exception as e:
			return None
if __name__ == "__main__": eleven()