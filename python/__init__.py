"""
Hook-to-Short Python Modules
Complete workflow for YouTube → Hook → Album Art → Short Video
"""

__version__ = "1.0.0"
__author__ = "Hook-to-Short Team"

from .mood_detector import MoodDetector, extract_metadata_from_title
from .kie_generator import KieAIGenerator
from .video_composer import VideoComposer, compose_complete_short
from .workflow import FulWorkflowOrchestrator

__all__ = [
    'MoodDetector',
    'extract_metadata_from_title',
    'KieAIGenerator',
    'VideoComposer',
    'compose_complete_short',
    'FulWorkflowOrchestrator',
]
