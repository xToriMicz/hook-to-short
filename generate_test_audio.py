"""Generate test audio file with chorus pattern for testing"""

from pydub import AudioSegment
import numpy as np

# Create test audio (60 seconds with chorus pattern)
sample_rate = 44100
duration_seconds = 60

# Create time array
t = np.arange(0, duration_seconds, 1/sample_rate)

# Create melody with chorus pattern
frequencies = []

# Verse 1 (20 seconds) - lower frequency
frequencies.extend([400] * (20 * sample_rate))

# Chorus 1 (10 seconds) - higher frequency (repeats)
frequencies.extend([600] * (10 * sample_rate))

# Verse 2 (10 seconds)
frequencies.extend([400] * (10 * sample_rate))

# Chorus 2 (10 seconds)
frequencies.extend([600] * (10 * sample_rate))

# Chorus 3 (10 seconds)
frequencies.extend([600] * (10 * sample_rate))

# Pad to correct length
if len(frequencies) < len(t):
    frequencies.extend([400] * (len(t) - len(frequencies)))

frequencies = frequencies[:len(t)]

# Create sine wave
audio_data = np.sin(2 * np.pi * np.array(frequencies, dtype=float) * t) * 32767 * 0.5

# Convert to 16-bit PCM
audio_data = audio_data.astype(np.int16)

# Create AudioSegment
audio = AudioSegment(
    audio_data.tobytes(),
    frame_rate=sample_rate,
    sample_width=2,
    channels=1
)

# Save as MP3
audio.export("test_song.mp3", format="mp3", bitrate="192k")
print(f"✓ Test audio file created: test_song.mp3 ({duration_seconds}s)")
print("  Structure: Verse→Chorus→Verse→Chorus→Chorus")
