import os
import sys
import logging
import argparse
from pychorus import find_and_output_chorus
from pydub import AudioSegment
from video_utils import create_short_video

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_input_file(file_path):
    """Validate that the input file exists and is of supported format."""
    if not os.path.exists(file_path):
        logger.error(f"Input file '{file_path}' does not exist.")
        return False
    
    supported_formats = ('.mp3', '.wav', '.flac', '.ogg', '.m4a')
    if not file_path.lower().endswith(supported_formats):
        logger.error(f"Unsupported format. Supported: {supported_formats}")
        return False
    
    return True

def extract_hook(input_file, output_file, clip_length=30):
    """
    Extracts the chorus from an audio file and saves it.
    
    Args:
        input_file (str): Path to the input audio file.
        output_file (str): Path to save the extracted hook.
        clip_length (int): Length of the hook to extract in seconds.
    
    Returns:
        bool: True if successful, False otherwise.
    """
    logger.info(f"Analyzing {input_file}...")
    
    if not validate_input_file(input_file):
        return False
    
    try:
        chorus_start = find_and_output_chorus(input_file, output_file, clip_length)
        
        if chorus_start is not None:
            logger.info(f"Successfully extracted hook starting at {chorus_start:.2f}s")
            logger.info(f"Hook saved to: {output_file}")
            return True
        else:
            logger.warning("Could not find a clear chorus in the audio.")
            return False
            
    except Exception as e:
        logger.error(f"Error during hook extraction: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Extract hook from music and create short video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract hook only
  python main.py input.mp3
  
  # Create short video with background
  python main.py input.mp3 -b background.mp4 -o output.mp4
        """
    )
    parser.add_argument("input", help="Path to input audio file (mp3, wav, flac, ogg, m4a)")
    parser.add_argument("-o", "--output", help="Path to output audio/video file")
    parser.add_argument("-l", "--length", type=int, default=30, help="Length of hook in seconds (default: 30)")
    parser.add_argument("-b", "--background", help="Path to background video file for creating short")
    parser.add_argument("-p", "--platform", choices=['tiktok', 'reels', 'youtube'], default='tiktok',
                        help="Target platform (default: tiktok)")
    
    args = parser.parse_args()
    
    # Generate output filename if not provided
    if not args.output:
        base, ext = os.path.splitext(args.input)
        args.output = f"{base}_hook{ext}"
    
    # Extract hook
    if not extract_hook(args.input, args.output, args.length):
        logger.error("Failed to extract hook.")
        sys.exit(1)
    
    # Create short video if background is provided
    if args.background:
        video_output = args.output.rsplit('.', 1)[0] + '.mp4'
        logger.info(f"Creating short video for {args.platform}...")
        if not create_short_video(args.output, args.background, video_output, platform=args.platform):
            logger.error("Failed to create short video.")
            sys.exit(1)
        logger.info("All done! Short video ready.")
    else:
        logger.info("Hook extraction complete. Use -b to add background video.")

if __name__ == "__main__":
    main()
