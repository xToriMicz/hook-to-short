"""
Configuration and presets for Hook-to-Short
"""

# Platform-specific presets for video creation
PLATFORM_PRESETS = {
    'tiktok': {
        'name': 'TikTok',
        'resolution': (1080, 1920),  # Width, Height (9:16 vertical)
        'fps': 30,
        'bitrate': '5000k',
        'audio_bitrate': '128k',
        'description': 'TikTok vertical video (1080x1920)'
    },
    'reels': {
        'name': 'Instagram Reels',
        'resolution': (1080, 1920),  # 9:16 vertical
        'fps': 30,
        'bitrate': '5000k',
        'audio_bitrate': '128k',
        'description': 'Instagram Reels vertical video (1080x1920)'
    },
    'youtube': {
        'name': 'YouTube',
        'resolution': (1920, 1080),  # 16:9 horizontal
        'fps': 60,
        'bitrate': '8000k',
        'audio_bitrate': '192k',
        'description': 'YouTube horizontal video (1920x1080)'
    },
    'youtube-short': {
        'name': 'YouTube Shorts',
        'resolution': (1080, 1920),  # 9:16 vertical
        'fps': 30,
        'bitrate': '5000k',
        'audio_bitrate': '128k',
        'description': 'YouTube Shorts vertical video (1080x1920)'
    }
}

# Audio file format support
SUPPORTED_AUDIO_FORMATS = ('.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma')

# Video file format support
SUPPORTED_VIDEO_FORMATS = ('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm')

# Default settings
DEFAULT_CONFIG = {
    'hook_length': 30,  # seconds
    'platform': 'tiktok',
    'fade_in_duration': 0.5,  # seconds
    'fade_out_duration': 0.5,  # seconds
}

# Text overlay defaults (for future feature)
TEXT_OVERLAY_CONFIG = {
    'font_size': 48,
    'font_color': 'white',
    'stroke_width': 2,
    'stroke_color': 'black',
    'position': 'bottom',  # top, center, bottom
}
