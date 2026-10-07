import json
import os
import signal
import sys

import sounddevice as sd
from vosk import Model, KaldiRecognizer
from usb_controller import XRPController

# Audio configuration (Vosk requires 16 kHz mono 16-bit PCM)
SAMPLE_RATE = 16000
CHUNK_SIZE = 3200  # 200 ms per chunk

# Vosk model directory (set VOSK_MODEL to override)
MODEL_PATH = os.environ.get("VOSK_MODEL", "vosk-model-small-en-us-0.15")

# Flag to handle clean shutdown on Ctrl+C
running = True


def signal_handler(sig, frame):
    global running
    print("\nStopping voice listener...")
    running = False


signal.signal(signal.SIGINT, signal_handler)

# Model must be downloaded and unzipped from
# https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
if not os.path.isdir(MODEL_PATH):
    print(f"Error: Vosk model not found at '{MODEL_PATH}'.")
    print("Download and unzip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip")
    sys.exit(1)

print(f"Loading Vosk model from {MODEL_PATH}...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)

try:
    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SIZE,
        dtype="int16",
        channels=1,
    )
except (sd.PortAudioError, OSError) as e:
    print(f"Error: Could not open microphone: {e}")
    print("Check available devices with 'arecord -l' and that libportaudio2 is installed.")
    sys.exit(1)

with XRPController() as bot:
    try:
        with stream:
            print("Listening... (Ctrl+C to stop)")
            while running:
                data, _overflowed = stream.read(CHUNK_SIZE)
                if recognizer.AcceptWaveform(bytes(data)):
                    # Utterance finished; Result() resets the recognizer
                    text = json.loads(recognizer.Result()).get("text", "").strip()
                    if text:
                        print(f"Heard: {text}")
                        resp = bot.send_command(f"TEXT,{text}")
                        print(f"  <- {resp}")
    finally:
        # Cut off the motors in case the robot was left driving
        bot.drive_stop()
        print("Stopped.")
