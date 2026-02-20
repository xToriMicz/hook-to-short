"""
Main Workflow Orchestrator
Coordinates: YouTube Download → Hook → Mood → Image Gen → Video Composition
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from python.mood_detector import MoodDetector, extract_metadata_from_title
from python.kie_generator import KieAIGenerator
from python.video_composer import VideoComposer, compose_complete_short

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FulWorkflowOrchestrator:
    """
    Complete workflow:
    YouTube URL → Download MP3 → Extract Hook → Detect Mood 
    → Generate Album Art → Compose Video
    """
    
    def __init__(
        self,
        downloads_folder: str = './downloads',
        outputs_folder: str = './outputs',
        kie_api_key: Optional[str] = None
    ):
        """Initialize workflow with paths and API keys"""
        self.downloads_folder = Path(downloads_folder)
        self.outputs_folder = Path(outputs_folder)
        
        # Create folders
        self.downloads_folder.mkdir(parents=True, exist_ok=True)
        self.outputs_folder.mkdir(parents=True, exist_ok=True)
        
        # Initialize modules
        self.mood_detector = MoodDetector()
        self.image_generator = KieAIGenerator(api_key=kie_api_key)
        self.video_composer = VideoComposer()
        
        logger.info("✓ Workflow Orchestrator initialized")
    
    def process_youtube_url(
        self,
        youtube_url: str,
        skip_download: bool = False
    ) -> Dict[str, str]:
        """
        Complete workflow from YouTube URL to short video
        
        Args:
            youtube_url: YouTube video/music URL
            skip_download: If True, assumes MP3 already exists
        
        Returns:
            Dict with paths to: hook_audio, generated_image, final_video
        """
        
        logger.info("=" * 70)
        logger.info("🎵 STARTING WORKFLOW ORCHESTRATOR")
        logger.info("=" * 70)
        
        result = {
            'status': 'failed',
            'youtube_url': youtube_url,
            'mp3_path': None,
            'song_title': None,
            'mood': None,
            'image_path': None,
            'hook_path': None,
            'video_path': None,
            'error': None,
        }
        
        try:
            # Step 1: Download audio from YouTube
            logger.info("\n📥 STEP 1: Downloading audio from YouTube...")
            mp3_path = self._download_youtube_audio(youtube_url)
            if not mp3_path:
                result['error'] = 'Failed to download YouTube audio'
                return result
            result['mp3_path'] = mp3_path
            
            # Step 2: Extract song metadata
            logger.info("\n📊 STEP 2: Extracting song metadata...")
            filename = Path(mp3_path).stem
            metadata = extract_metadata_from_title(filename)
            song_title = metadata['song']
            artist = metadata['artist']
            result['song_title'] = song_title
            
            logger.info(f"   🎵 Song: {song_title}")
            logger.info(f"   🎤 Artist: {artist}")
            
            # Step 3: Detect mood
            logger.info("\n🎭 STEP 3: Detecting song mood...")
            mood_info = self.mood_detector.detect_from_artist_title(artist, song_title)
            mood = mood_info['mood']
            intensity = mood_info['intensity']
            result['mood'] = mood
            
            logger.info(f"   • Mood: {mood}")
            logger.info(f"   • Intensity: {intensity}")
            
            # Step 4: Extract hook from audio
            logger.info("\n🎵 STEP 4: Extracting hook from audio...")
            hook_path = self._extract_hook(mp3_path, song_title)
            if not hook_path:
                result['error'] = 'Failed to extract hook'
                return result
            result['hook_path'] = hook_path
            
            # Step 5: Generate album art with AI
            logger.info("\n🎨 STEP 5: Generating album art with Kie.ai...")
            image_path = self._generate_album_art(song_title, mood, intensity)
            if not image_path:
                result['error'] = 'Failed to generate album art'
                return result
            result['image_path'] = image_path
            
            # Step 6: Compose final video
            logger.info("\n🎬 STEP 6: Composing final short video...")
            video_path = self._compose_video(image_path, hook_path, song_title)
            if not video_path:
                result['error'] = 'Failed to compose video'
                return result
            result['video_path'] = video_path
            
            # Success!
            result['status'] = 'success'
            
            logger.info("\n" + "=" * 70)
            logger.info("✓ WORKFLOW COMPLETED SUCCESSFULLY!")
            logger.info("=" * 70)
            logger.info(f"📹 Final Video: {video_path}")
            logger.info("=" * 70)
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Workflow failed: {e}")
            import traceback
            traceback.print_exc()
            result['error'] = str(e)
            return result
    
    def _download_youtube_audio(self, youtube_url: str) -> Optional[str]:
        """Download audio from YouTube"""
        try:
            import subprocess
            
            temp_file = self.downloads_folder / "%(title)s.%(ext)s"
            
            cmd = [
                'python', '-m', 'yt_dlp',
                '-f', 'bestaudio',
                '-x',
                '--audio-format', 'mp3',
                '--audio-quality', '192K',
                '-o', str(temp_file),
                '--no-playlist',
                youtube_url
            ]
            
            logger.info(f"   Running: {' '.join(cmd[:5])}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"   Error: {result.stderr}")
                return None
            
            # Find downloaded MP3
            mp3_files = list(self.downloads_folder.glob('*.mp3'))
            if mp3_files:
                mp3_path = mp3_files[-1]  # Latest file
                logger.info(f"   ✓ Downloaded: {mp3_path.name}")
                return str(mp3_path)
            
            logger.error("   No MP3 file found after download")
            return None
        
        except Exception as e:
            logger.error(f"   Error downloading audio: {e}")
            return None
    
    def _extract_hook(self, audio_path: str, song_title: str, length_sec: int = 30) -> Optional[str]:
        """Extract hook from audio using main.py"""
        try:
            import subprocess
            
            hook_filename = f"{song_title.replace(' ', '_')}_hook.mp3"
            hook_path = self.outputs_folder / hook_filename
            
            # Call main.py directly
            cmd = [
                'python', 'python/main.py',
                audio_path,
                '-o', str(hook_path),
                '-l', str(length_sec)
            ]
            
            logger.info(f"   Running: python main.py ... -l {length_sec}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and hook_path.exists():
                logger.info(f"   ✓ Hook extracted: {hook_path.name}")
                return str(hook_path)
            else:
                logger.error(f"   Hook extraction failed")
                if result.stderr:
                    logger.error(f"   Error: {result.stderr}")
                return None
        
        except Exception as e:
            logger.error(f"   Error extracting hook: {e}")
            return None
    
    def _generate_album_art(self, song_title: str, mood: str, intensity: str) -> Optional[str]:
        """Generate album art using Kie.ai"""
        try:
            output_filename = f"{song_title.replace(' ', '_')}_art.png"
            output_path = self.outputs_folder / output_filename
            
            image_path = self.image_generator.generate_album_art(
                song_title=song_title,
                mood=mood,
                intensity=intensity,
                output_path=str(output_path)
            )
            
            if image_path:
                logger.info(f"   ✓ Generated: {Path(image_path).name}")
            
            return image_path
        
        except Exception as e:
            logger.error(f"   Error generating album art: {e}")
            return None
    
    def _compose_video(self, image_path: str, hook_path: str, song_title: str) -> Optional[str]:
        """Compose final short video"""
        try:
            output_filename = f"{song_title.replace(' ', '_')}_short.mp4"
            output_path = self.outputs_folder / output_filename
            
            video_path = compose_complete_short(
                image_path=image_path,
                hook_audio_path=hook_path,
                output_path=str(output_path),
                song_title=song_title,
                platform='tiktok'
            )
            
            return video_path
        
        except Exception as e:
            logger.error(f"   Error composing video: {e}")
            return None


# ==================== Example Usage ====================

if __name__ == '__main__':
    # Example: Process a YouTube URL
    
    orchestrator = FulWorkflowOrchestrator(
        downloads_folder='./downloads',
        outputs_folder='./outputs',
        kie_api_key=None
    )
    
    # Test with a URL (replace with real link)
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Example
    
    result = orchestrator.process_youtube_url(youtube_url)
    
    # Print results
    print("\n" + "=" * 70)
    print("WORKFLOW RESULT:")
    print("=" * 70)
    print(json.dumps(result, indent=2))
