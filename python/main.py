"""
Hook extraction from audio - main entry point
This is called by workflow.py to extract hooks from MP3 files
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

import soundfile as _sf
if not hasattr(_sf, 'SoundFileRuntimeError'):
    _sf.SoundFileRuntimeError = RuntimeError

try:
    from pychorus import find_and_output_chorus
except ImportError:
    print("⚠️  pychorus not installed. Install with: pip install pychorus")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ('.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac')

def validate_input_file(file_path):
    """Validate input file exists and is supported format"""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    if not file_path.lower().endswith(SUPPORTED_FORMATS):
        logger.error(f"Unsupported format. Supported: {SUPPORTED_FORMATS}")
        return False
    
    return True

def extract_hook(input_file, output_file, clip_length=30):
    """
    Extract the chorus/hook from audio file

    Uses a small search window (15s) for chorus detection,
    then outputs the requested clip_length from that position.

    Args:
        input_file: Path to input audio
        output_file: Where to save hook
        clip_length: Length in seconds of the output clip

    Returns:
        bool: Success status
    """
    logger.info(f"🎵 Analyzing {Path(input_file).name}...")

    if not validate_input_file(input_file):
        return False

    try:
        # Always detect chorus with 15s search window (reliable),
        # then cut clip_length from that position
        from pychorus.helpers import create_chroma, find_chorus
        import soundfile as sf

        chroma, song_wav_data, sr, song_length_sec = create_chroma(input_file)

        # Use 15s for detection — works reliably
        DETECT_LENGTH = 15
        chorus_start = find_chorus(chroma, sr, song_length_sec, DETECT_LENGTH)

        if chorus_start is None:
            logger.warning("Could not find clear chorus in audio")
            return False

        logger.info(f"Chorus found at {chorus_start:.2f}s")

        # Clamp end to song length
        end_sec = min(chorus_start + clip_length, song_length_sec)
        actual_length = end_sec - chorus_start

        chorus_data = song_wav_data[int(chorus_start * sr):int(end_sec * sr)]
        sf.write(output_file, chorus_data, sr)

        logger.info(f"Hook extracted: {actual_length:.1f}s from {chorus_start:.2f}s")
        logger.info(f"Saved to: {output_file}")
        return True

    except Exception as e:
        logger.error(f"Error extracting hook: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Extract music hook/chorus from audio file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py input.mp3
  python main.py input.mp3 -o hook.mp3 -l 20
        """
    )
    
    parser.add_argument(
        "input",
        help="Path to input audio file (mp3, wav, flac, ogg, m4a, aac)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Path to output hook file (optional)"
    )
    parser.add_argument(
        "-l", "--length",
        type=int,
        default=30,
        help="Hook duration in seconds (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Generate output filename if not provided
    if not args.output:
        base, ext = os.path.splitext(args.input)
        args.output = f"{base}_hook{ext}"
    
    # Extract hook
    success = extract_hook(args.input, args.output, args.length)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
