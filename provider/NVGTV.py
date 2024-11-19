from provider import star_provider
star_provider("NVGTProvider", voices = "NVGT Fallback Voice RSynth", synthesis_process = ["nvgtv", "{filename}", "{text}"])
