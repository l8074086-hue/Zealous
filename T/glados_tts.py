import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
import io
import queue
import threading


class GLaDOS:
    def __init__(self, model_path):
        self.voice = PiperVoice.load(model_path)
        self.enabled = True

    def get_audio_stream(self, text):
        if not self.enabled:
            return None
        buf = io.BytesIO()
        for chunk in self.voice.synthesize(text):
            buf.write(chunk.audio_int16_bytes)
        buf.seek(0)
        return buf

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled
