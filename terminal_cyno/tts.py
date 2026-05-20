from faster_whisper import WhisperModel

# 1. Choose a model size
# Available models are tiny, base, small, medium, large,
# tiny.en, base.en, small.en, medium.en.
model_size = "base.en"

# 2. Initialize the model
# The model will be downloaded automatically the first time it is used.
# Specify 'cpu' or 'gpu' for the device, and adjust compute_type as needed.
model = WhisperModel(model_size, device="cpu", compute_type="int8") # Use "cuda" for GPU

# 3. Transcribe the audio file
audio_file = "your_audio_file.wav"
segments, info = model.transcribe(audio_file, beam_size=5)

# 4. Print the transcription
print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
for segment in segments:
    print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
