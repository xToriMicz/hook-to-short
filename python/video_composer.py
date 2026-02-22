"""
Video Composition - Combine image + audio into vertical short video
Uses ffmpeg directly (no moviepy dependency)
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VideoComposer:
    """Compose short videos from images and audio using ffmpeg"""

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
        Create short video from image + audio using ffmpeg.

        Returns:
            Path to created video or None if failed
        """
        try:
            logger.info(f"Creating short video: {song_title}")

            if not Path(image_path).exists():
                logger.error(f"Image not found: {image_path}")
                return None

            if not Path(audio_path).exists():
                logger.error(f"Audio not found: {audio_path}")
                return None

            settings = self.PLATFORMS.get(platform, self.PLATFORMS['tiktok'])
            width, height = settings['resolution']

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Get audio duration for fade-out calculation
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                audio_path,
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            duration = float(probe_result.stdout.strip())
            fade_out = max(0, duration - 0.5)

            # ffmpeg: loop image + overlay audio, fade in/out, fit to 9:16
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", image_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", settings['audio_bitrate'],
                "-b:v", settings['bitrate'],
                "-r", str(settings['fps']),
                "-pix_fmt", "yuv420p",
                "-vf", (
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"fade=t=in:st=0:d=0.5,"
                    f"fade=t=out:st={fade_out}:d=0.5"
                ),
                "-af", f"afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out}:d=0.5",
                "-shortest",
                "-movflags", "+faststart",
                output_path,
            ]

            logger.info(f"Running ffmpeg...")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr[-500:]}")
                return None

            logger.info(f"Video created: {output_path}")
            return output_path

        except subprocess.TimeoutExpired:
            logger.error("ffmpeg timed out (5 min)")
            return None
        except FileNotFoundError:
            logger.error("ffmpeg not found — install ffmpeg or ensure it's in PATH")
            return None
        except Exception as e:
            logger.error(f"Error creating video: {e}")
            return None


def compose_complete_short(
    image_path: str,
    hook_audio_path: str,
    output_path: str,
    song_title: str = "",
    platform: str = 'tiktok'
) -> Optional[str]:
    """
    Complete workflow: image + hook → short video

    Returns:
        Path to completed video
    """
    logger.info("=" * 60)
    logger.info("COMPOSING SHORT VIDEO")
    logger.info("=" * 60)

    composer = VideoComposer()

    result = composer.create_short_video(
        image_path=image_path,
        audio_path=hook_audio_path,
        output_path=output_path,
        song_title=song_title,
        platform=platform,
    )

    if result:
        logger.info("=" * 60)
        logger.info(f"SUCCESS: {result}")
        logger.info("=" * 60)

    return result
