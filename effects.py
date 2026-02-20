"""
Video effects and enhancements for Hook-to-Short
"""

import logging
try:
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ImageClip, concatenate_videoclips
except ImportError:
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip
        from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
        from moviepy.video.VideoClip import TextClip
        from moviepy.video.io.ImageSequenceClip import ImageClip
        from moviepy.video.compositing.concatenate import concatenate_videoclips
    except ImportError:
        pass

from config import TEXT_OVERLAY_CONFIG

logger = logging.getLogger(__name__)


def add_text_overlay(video_clip, text, duration=None, **kwargs):
    """
    Add text overlay to video.
    
    Args:
        video_clip: MoviePy VideoFileClip
        text (str): Text to display
        duration (float): Duration of text display (default: video duration)
        **kwargs: Additional text styling options
        - font_size, font_color, stroke_width, stroke_color, position
    
    Returns:
        CompositeVideoClip with text overlay
    """
    logger.info(f"Adding text overlay: '{text}'")
    
    try:
        if duration is None:
            duration = video_clip.duration
        
        # Merge config with kwargs
        config = TEXT_OVERLAY_CONFIG.copy()
        config.update(kwargs)
        
        # Create text clip
        txt_clip = TextClip(
            text=text,
            fontsize=config['font_size'],
            color=config['font_color'],
            stroke_width=config['stroke_width'],
            stroke_color=config['stroke_color'],
            method='caption',  # Use caption to handle long text
            size=(video_clip.w - 40, None)  # Leave margins
        ).with_duration(duration)
        
        # Position text
        position_map = {
            'top': ('center', 30),
            'center': ('center', 'center'),
            'bottom': ('center', video_clip.h - txt_clip.h - 30)
        }
        
        txt_clip = txt_clip.with_position(position_map.get(config['position'], ('center', 'center')))
        
        # Create composite
        final = CompositeVideoClip([video_clip, txt_clip])
        return final
        
    except Exception as e:
        logger.error(f"Error adding text overlay: {e}")
        return video_clip


def add_fade_effects(video_clip, fade_in_duration=0.5, fade_out_duration=0.5):
    """
    Add fade in and fade out effects.
    
    Args:
        video_clip: MoviePy VideoFileClip
        fade_in_duration (float): Duration of fade in
        fade_out_duration (float): Duration of fade out
    
    Returns:
        VideoFileClip with fade effects
    """
    logger.info(f"Adding fade effects ({fade_in_duration}s in, {fade_out_duration}s out)")
    
    try:
        faded = video_clip.with_start(0)
        
        # Apply fade in
        if fade_in_duration > 0:
            faded = faded.with_make_frame(
                lambda get_frame, t: get_frame(t) if t > fade_in_duration else get_frame(t) * (t / fade_in_duration)
            )
        
        # Apply fade out
        if fade_out_duration > 0:
            start_fade = video_clip.duration - fade_out_duration
            faded = faded.with_make_frame(
                lambda get_frame, t: (
                    get_frame(t) if t < start_fade 
                    else get_frame(t) * (1 - (t - start_fade) / fade_out_duration)
                )
            )
        
        return faded
        
    except Exception as e:
        logger.error(f"Error adding fade effects: {e}")
        return video_clip


def add_watermark(video_clip, watermark_path, position='bottom-right', scale=0.3):
    """
    Add watermark/logo to video.
    
    Args:
        video_clip: MoviePy VideoFileClip
        watermark_path (str): Path to watermark image
        position (str): Position - top-left, top-right, bottom-left, bottom-right
        scale (float): Scale of watermark (0-1 relative to video width)
    
    Returns:
        CompositeVideoClip with watermark
    """
    logger.info(f"Adding watermark from {watermark_path}")
    
    try:
        from moviepy import ImageClip
        
        watermark = ImageClip(watermark_path).with_duration(video_clip.duration)
        
        # Scale watermark
        watermark_width = int(video_clip.w * scale)
        watermark = watermark.resize(width=watermark_width)
        
        # Position map
        position_map = {
            'top-left': (10, 10),
            'top-right': (video_clip.w - watermark.w - 10, 10),
            'bottom-left': (10, video_clip.h - watermark.h - 10),
            'bottom-right': (video_clip.w - watermark.w - 10, video_clip.h - watermark.h - 10)
        }
        
        watermark = watermark.with_position(position_map.get(position, ('bottom-right')))
        
        # Create composite
        final = CompositeVideoClip([video_clip, watermark])
        return final
        
    except Exception as e:
        logger.error(f"Error adding watermark: {e}")
        return video_clip


def speed_up_video(video_clip, speed_factor=1.25):
    """
    Speed up video playback.
    
    Args:
        video_clip: MoviePy VideoFileClip
        speed_factor (float): Speed multiplier (1.25 = 25% faster)
    
    Returns:
        VideoFileClip with adjusted speed
    """
    logger.info(f"Speeding up video by {speed_factor}x")
    
    try:
        if speed_factor <= 0:
            logger.error("Speed factor must be positive")
            return video_clip
        
        return video_clip.speedx(speed_factor)
        
    except Exception as e:
        logger.error(f"Error speeding up video: {e}")
        return video_clip
