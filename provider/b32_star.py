import os
import subprocess
from provider import star_provider

class b32_star(star_provider):
	def get_voices(self):
		return {i + " Keynote": {"full_name": i} for i in subprocess.run([os.path.join(os.path.abspath(os.path.dirname(__file__)), "b32_spk"), "-v?"], shell = True, capture_output = True, text = True).stdout.split("\n")[1:-1]}

if __name__ == "__main__":
	b32_star("b32_star", synthesis_process = [os.path.join(os.path.abspath(os.path.dirname(__file__)), "b32_spk"), "-v{voice}", "-f{filename}", "-t{text}"], synthesis_process_rate = ["-r{rate}"])
