import os
import logging
try:
    from moviepy.editor import VideoFileClip, AudioFileClip
except ImportError:
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip
        from moviepy.audio.AudioFileClip import AudioFileClip
    except ImportError:
        pass

logger = logging.getLogger(__name__)

# Platform-specific presets
PLATFORM_PRESETS = {
    'tiktok': {
        'resolution': (1080, 1920),  # 9:16 vertical
        'fps': 30,
        'bitrate': '5000k',
        'audio_bitrate': '128k'
    },
    'reels': {
        'resolution': (1080, 1920),  # 9:16 vertical
        'fps': 30,
        'bitrate': '5000k',
        'audio_bitrate': '128k'
    },
    'youtube': {
        'resolution': (1920, 1080),  # 16:9 horizontal
        'fps': 60,
        'bitrate': '8000k',
        'audio_bitrate': '192k'
    }
}

def validate_files(audio_path, video_path):
    """Validate that both audio and video files exist."""
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found: {audio_path}")
        return False
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        return False
    return True

def create_short_video(audio_hook_path, background_video_path, output_video_path, platform='tiktok'):
    """
    Combines a background video with the extracted audio hook to create a short.
    
    Args:
        audio_hook_path (str): Path to extracted audio hook
        background_video_path (str): Path to background video
        output_video_path (str): Output video path
        platform (str): Target platform (tiktok, reels, youtube)
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Creating short video for {platform}...")
    
    if not validate_files(audio_hook_path, background_video_path):
        return False
    
    preset = PLATFORM_PRESETS.get(platform, PLATFORM_PRESETS['tiktok'])
    
    try:
        logger.info("Loading audio file...")
        audio = AudioFileClip(audio_hook_path)
        
        logger.info("Loading video file...")
        video = VideoFileClip(background_video_path)
        
        # Ensure video duration matches audio
        if video.duration < audio.duration:
            logger.warning(
                f"Video duration ({video.duration:.1f}s) is shorter than audio ({audio.duration:.1f}s). "
                "Video will be looped if needed."
            )
        
        # Resize to platform preset
        video_resized = video.resized(newsize=preset['resolution']).with_subclip(0, audio.duration)
        
        # Add audio to video
        final_video = video_resized.with_audio(audio)
        
        logger.info(f"Writing video file with {preset['fps']}fps, bitrate {preset['bitrate']}...")
        final_video.write_videofile(
            output_video_path,
            fps=preset['fps'],
            codec="libx264",
            audio_codec="aac",
            bitrate=preset['bitrate'],
            audio_bitrate=preset['audio_bitrate'],
            verbose=False,
            logger=None
        )
        
        logger.info(f"Short video created successfully: {output_video_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating video: {e}")
        return False
    
    finally:
        # Clean up resources
        try:
            if 'audio' in locals():
                audio.close()
            if 'video' in locals():
                video.close()
            if 'final_video' in locals():
                final_video.close()
        except Exception as cleanup_error:
            logger.warning(f"Error during cleanup: {cleanup_error}")
