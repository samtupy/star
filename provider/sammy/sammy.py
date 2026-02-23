import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from provider import star_provider
star_provider("sammy", voices = "microsam", synthesis_process = [os.path.join(os.path.dirname(__file__), "sam"), "-wav", "{filename}", "{text}"], synthesis_process_rate = ["-speed", "{rate}"], synthesis_process_pitch = ["-pitch", "{pitch}"])
