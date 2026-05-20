import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice
import io
import queue
import threading


class GLaDOS:
    def __init__(self, model_path):
        # Load the Piper model
        self.voice = PiperVoice.load(model_path)
        self.enabled = True  # Set to True so he starts vocal

    def get_audio_stream(self, text):
        """Synthesizes text and returns a BytesIO stream of raw PCM bytes."""
        if not self.enabled:
            return None

        # We collect all chunks into one buffer for the Discord player
        buf = io.BytesIO()
        for chunk in self.voice.synthesize(text):
            buf.write(chunk.audio_int16_bytes)
        buf.seek(0)
        return buf

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled
