import atexit, miniaudio, time

class playsound:
	def __init__(self, data, pitch = 1.0, finish_func = None, finish_func_data = None):
		self.finish_func = finish_func
		self.finish_func_data = finish_func_data
		self.device = miniaudio.PlaybackDevice(buffersize_msec = 5, sample_rate = int(44100 * pitch))
		atexit.register(self.device.close)
		if type(data) == bytes: self.stream = miniaudio.stream_with_callbacks(miniaudio.stream_memory(data), end_callback = self.on_stream_end)
		else: self.stream = miniaudio.stream_with_callbacks(miniaudio.stream_file(data, sample_rate = 44100), end_callback = self.on_stream_end)
		next(self.stream)
		self.device.start(self.stream)
	def __del__(self): self.close()
	def on_stream_end(self):
		self.close()
		if self.finish_func: self.finish_func(self.finish_func_data)
	@property
	def playing(self): return self.device is not None and self.device.running
	def pause(self):
		if not self.playing: return False
		self.device.stop()
		return True
	def resume(self):
		if not self.device or self.playing: return False
		self.device.start(self.stream)
		return True
	def close(self):
		if not self.device: return
		atexit.unregister(self.device.close)
		self.device.close()
		self.device = None

playsound("audio/ready.ogg", pitch = 0.7)
s = playsound("audio/voices_connect.ogg", pitch = 0.9)
for i in range(20): 
	time.sleep(0.05)
	s.pause() if s.playing else s.resume()
time.sleep(5)
