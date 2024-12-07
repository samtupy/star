from provider import star_provider
star_provider("sammy", voices = "microsam", synthesis_process = ["sam", "-wav", "{filename}", "{text}"], synthesis_process_rate = ["-speed", "{rate}"], synthesis_process_pitch = ["-pitch", "{pitch}"])
