import sys
from pathlib import Path

try:
    from faster_whisper import WhisperModel
    print("faster-whisper is installed!")
    
    # Try initializing a tiny model to see if it works
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    print("Loaded tiny model successfully!")
except Exception as e:
    print(f"Failed: {e}")
