import subprocess
from provider import star_provider

class balcony(star_provider):
	def get_voices(self):
		raw = subprocess.run(["balcon", "-l"], shell = True, capture_output = True, text = True).stdout.split("\n")
		voices = []
		for v in raw:
			if not v or not v.startswith(" "): continue
			voice = v
			if "::" in voice: voice = voice[voice.find("::") + 3:]
			voices.append(voice.strip())
		return voices

if __name__ == "__main__":
	balcony("balcony", synthesis_process = ["balcon", "-n", "{voice}", "-t", "{text}", "-w", "{filename}"], synthesis_process_rate = ["-s", "{rate}"], synthesis_process_pitch = ["-p", "{pitch}"])
