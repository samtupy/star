import subprocess
from provider import star_provider

voices = subprocess.run("say -v ?", shell = True, capture_output = True, text = True).stdout.split("\n")[:-1]
for i in range(len(voices)):
	voices[i] = voices[i].partition("#")[0].strip().rpartition(" ")[0].strip()
voices.sort()

star_provider("macsay", voices = voices, synthesis_process = ["say", "-o", "{filename}", "--data-format=LEI16@32000", "-v", "{voice}", "{text}"], synthesis_process_rate = ["-r", "{rate}"])
