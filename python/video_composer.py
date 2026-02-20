"""
Video Composition - Combine image + audio into vertical short video
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from moviepy.editor import (
        ImageClip, AudioFileClip, CompositeVideoClip, vfx
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    logger.warning("moviepy not available - install with: pip install moviepy")


class VideoComposer:
    """Compose short videos from images and audio"""
    
    PLATFORMS = {
        'tiktok': {
            'resolution': (1080, 1920),
            'fps': 30,
            'bitrate': '5000k',
            'audio_bitrate': '128k',
        },
        'reels': {
            'resolution': (1080, 1920),
            'fps': 30,
            'bitrate': '5000k',
            'audio_bitrate': '128k',
        },
        'youtube-short': {
            'resolution': (1080, 1920),
            'fps': 30,
            'bitrate': '5000k',
            'audio_bitrate': '128k',
        },
    }
    
    def __init__(self):
        if not MOVIEPY_AVAILABLE:
            raise ImportError("moviepy is required for video composition")
    
    def create_short_video(
        self,
        image_path: str,
        audio_path: str,
        output_path: str,
        song_title: str = "",
        platform: str = 'tiktok',
        add_watermark: bool = False
    ) -> Optional[str]:
        """
        Create short video from image + audio
        
        Args:
            image_path: Path to generated image
            audio_path: Path to extracted hook audio
            output_path: Where to save video
            song_title: Song title for watermark/credit
            platform: 'tiktok', 'reels', 'youtube-short'
            add_watermark: Add watermark text
        
        Returns:
            Path to created video or None if failed
        """
        try:
            logger.info(f"🎬 Creating short video: {song_title}")
            
            if not Path(image_path).exists():
                logger.error(f"Image not found: {image_path}")
                return None
            
            if not Path(audio_path).exists():
                logger.error(f"Audio not found: {audio_path}")
                return None
            
            # Get platform settings
            settings = self.PLATFORMS.get(platform, self.PLATFORMS['tiktok'])
            
            # Load audio
            logger.info(f"📥 Loading audio: {audio_path}")
            audio = AudioFileClip(audio_path)
            duration = audio.duration
            
            # Load and resize image to fit platform
            logger.info(f"📥 Loading image: {image_path}")
            image = ImageClip(image_path).set_duration(duration)
            
            # Resize to platform resolution
            width, height = settings['resolution']
            image = image.resize(width=width, height=height)
            
            # Add fade effects
            logger.info("✨ Adding fade effects...")
            fade_duration = 0.5
            
            # Fade in
            def fade_in(get_frame, t):
                if t < fade_duration:
                    return get_frame(t) * (t / fade_duration)
                return get_frame(t)
            
            # Fade out
            def fade_out(get_frame, t):
                fade_start = duration - fade_duration
                if t > fade_start:
                    return get_frame(t) * (1 - (t - fade_start) / fade_duration)
                return get_frame(t)
            
            # Apply both fades
            image_faded = image.set_make_frame(
                lambda t: fade_out(
                    lambda _t: fade_in(image.get_frame, _t),
                    t
                )
            )
            
            # Add optional watermark/title
            if add_watermark and song_title:
                logger.info("🏷️  Adding title watermark...")
                txt = TextClip(
                    song_title,
                    fontsize=48,
                    color='white',
                    method='caption',
                    size=(width - 60, None),
                    font='Arial-Bold'
                ).set_duration(duration).set_position(('center', height - 100))
                
                image_faded = CompositeVideoClip([image_faded, txt])
            
            # Create final video with audio
            logger.info("🎵 Adding audio...")
            final_video = image_faded.set_audio(audio)
            
            # Export video
            logger.info(f"💾 Exporting video to: {output_path}")
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            final_video.write_videofile(
                output_path,
                fps=settings['fps'],
                codec='libx264',
                audio_codec='aac',
                bitrate=settings['bitrate'],
                audio_bitrate=settings['audio_bitrate'],
                verbose=False,
                logger=None,
                preset='medium'
            )
            
            logger.info(f"✓ Video created: {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Error creating video: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        finally:
            # Cleanup
            try:
                if 'audio' in locals():
                    audio.close()
                if 'image' in locals():
                    image.close()
                if 'final_video' in locals():
                    final_video.close()
            except:
                pass


def compose_complete_short(
    image_path: str,
    hook_audio_path: str,
    output_path: str,
    song_title: str = "",
    platform: str = 'tiktok'
) -> Optional[str]:
    """
    Complete workflow: image + hook → short video
    
    Args:
        image_path: Generated album art
        hook_audio_path: Extracted hook audio
        output_path: Output video path
        song_title: Song title for credits
        platform: Target platform
    
    Returns:
        Path to completed video
    """
    logger.info("=" * 60)
    logger.info("🎬 COMPOSING SHORT VIDEO")
    logger.info("=" * 60)
    
    composer = VideoComposer()
    
    result = composer.create_short_video(
        image_path=image_path,
        audio_path=hook_audio_path,
        output_path=output_path,
        song_title=song_title,
        platform=platform,
        add_watermark=False  # Text already in AI-generated image from Kie.ai
    )
    
    if result:
        logger.info("=" * 60)
        logger.info(f"✓ SUCCESS: {result}")
        logger.info("=" * 60)
    
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Test
    composer = VideoComposer()
    
    # Would need actual paths to test
    # result = composer.create_short_video(
    #     image_path="test.png",
    #     audio_path="test.mp3",
    #     output_path="output.mp4",
    #     song_title="Test Song",
    #     platform='tiktok'
    # )
