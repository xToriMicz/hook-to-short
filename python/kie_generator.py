"""
Kie.ai Image Generation using Nanobanana Pro Model
Generates album art/background images for short videos
"""

import os
import requests
import logging
import time
import math
from pathlib import Path
from typing import Optional, Dict
import json

logger = logging.getLogger(__name__)

class KieAIGenerator:
    """Generate images using kie.ai Nanobanana Pro API"""

    # Kie.ai API configuration
    API_URL = "https://api.kie.ai/api/v1/jobs/createTask"
    MODEL = "nano-banana-pro"
    POLL_URL = "https://api.kie.ai/api/v1/playground/recordInfo"
    POLL_TIMEOUT = 180  # max seconds to wait

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from .env or parameter"""
        self.api_key = api_key or os.environ.get("KIE_API_KEY", "")
        if not self.api_key:
            logger.error("Kie.ai API key not configured — set KIE_API_KEY in .env")

    FONT_STYLES = {
        "ลายมือพู่กัน": "Thai handwritten brush calligraphy, smooth flowing strokes, natural thick-thin variation, soft emotional mood, warm romantic and nostalgic feeling, handwritten title style",
        "โปสเตอร์หนังไทย": "Thai classic movie poster typography, bold Thai display font, vivid red color, sharp clean edges, vintage Thai cinema style, high readability retro poster look",
        "โค้งมน ชิลคาเฟ่": "Thai rounded handwritten display font, soft curved letterforms, thick and easy-to-read strokes, chill playlist style, cozy cafe mood, friendly and casual typography",
        "ชอล์กอินดี้": "Thai handwritten chalk brush typography, rough broken brush strokes, chalk-like texture, raw handmade lettering, indie aesthetic, lonely and emotional mood",
        "ชอล์กกระดานดำ": "Thai chalk handwritten typography, rough grainy strokes, powdery broken edges, blackboard writing style, quiet and contemplative mood, deep and thoughtful feeling",
        "ลายมืออินดี้": "Thai indie handwritten typography, natural imperfect strokes, casual hand-drawn lettering, folk music aesthetic, lonely yet warm mood, authentic handwritten feel",
        "พู่กันสะบัดแรง": "Thai expressive brush calligraphy, fast energetic brush strokes, strong flicks and dynamic movement, clear thick-thin contrast, emotional and powerful handwriting",
        "พู่กันโรแมนติก": "Thai romantic brush calligraphy, smooth continuous strokes, beautiful thick-thin variation, well-controlled rhythm, warm and romantic mood, elegant handwritten lettering",
        "พู่กันธรรมชาติ": "Thai organic brush calligraphy, slightly broken natural strokes, visible hand rhythm, uneven thick-thin variation, calm deep and sincere mood, honest handcrafted lettering",
        "คลาสสิก มีเชิง": "Thai classical serif display typography, elegant traditional letterforms, sharp clean strokes, balanced proportions, refined and warm aesthetic",
        "โค้งมน นุ่มนวล": "Thai soft decorative handwritten typography, rounded smooth letterforms, gentle strokes with moderate thick-thin balance, warm and romantic feeling, friendly and elegant style",
        "พู่กันเส้นยาว": "Thai handwritten brush calligraphy, long continuous strokes, natural pressure-based thick-thin variation, rounded stroke endings with trailing tails, raw emotional mood, lonely and realistic handwritten style",
        "Cursive โรแมนติก": "Thai handwritten calligraphy typography, soft brush pen strokes, flowing cursive Thai letters, natural uneven strokes, romantic and nostalgic mood, handwritten title style, gentle curves, emotional handwriting",
        "Bold Grunge": "Thai bold sans-serif typography, rough grainy texture, powdery edges, chalk-like broken strokes, slightly blurred distressed text, grunge Thai typography style, raw emotional text",
        "Modern Brush": "Thai modern handwritten brush typography, bold expressive strokes, clear thick-thin contrast, casual and friendly style",
    }

    def generate_album_art(
        self,
        song_title: str,
        mood: str,
        intensity: str = 'medium',
        output_path: Optional[str] = None,
        video_style: str = 'Thai',
        font_style: str = 'ลายมือพู่กัน',
        font_angle: str = 'เฉียงขึ้น',
        artist: str = '',
    ) -> Optional[str]:
        """
        Generate album art image from song info

        Returns:
            Path to generated image or None if failed
        """
        try:
            logger.info(f"Generating album art for: {song_title} by {artist} (style: {video_style}, font: {font_style})")

            prompt = self._build_prompt(song_title, mood, intensity, video_style, font_style, font_angle, artist)

            payload = {
                "model": self.MODEL,
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": "9:16",
                    "resolution": "1K",
                    "output_format": "png",
                },
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            logger.info("Sending request to Kie.ai...")

            response = requests.post(
                self.API_URL,
                data=json.dumps(payload),
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(f"API Error {response.status_code}: {response.text}")
                return None

            result = response.json()

            # Async API — extract task ID and poll for result
            task_id = (
                result.get("data", {}).get("taskId")
                or result.get("taskId")
                or result.get("id")
            )

            # If response already contains an image URL, use it directly
            image_url = (
                result.get("data", {}).get("url")
                or result.get("data", {}).get("output", {}).get("image_url")
            )
            if image_url:
                return self._download_image(image_url, output_path, song_title)

            if not task_id:
                logger.error(f"No taskId in response: {result}")
                return None

            logger.info(f"Task created: {task_id}")

            # Poll for completion
            image_url = self._poll_task(task_id, headers)
            if image_url:
                return self._download_image(image_url, output_path, song_title)

            return None

        except Exception as e:
            logger.error(f"Error generating album art: {e}")
            return None

    def _poll_task(self, task_id: str, headers: dict) -> Optional[str]:
        """Poll task status until complete or timeout (exponential backoff)"""
        elapsed = 0
        interval = 2  # start at 2s
        max_interval = 8

        while elapsed < self.POLL_TIMEOUT:
            time.sleep(interval)
            elapsed += interval

            try:
                poll_url = f"{self.POLL_URL}?taskId={task_id}"
                resp = requests.get(
                    poll_url,
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.warning(f"Poll status {resp.status_code}, retrying... ({elapsed}s)")
                    continue

                data = resp.json()
                status = (
                    data.get("data", {}).get("state")
                    or data.get("data", {}).get("status")
                    or data.get("status")
                )
                logger.info(f"Task {task_id[:12]}...: {status} ({elapsed}s)")

                if status in ("completed", "success", "done"):
                    task_data = data.get("data", {})
                    # Kie.ai returns URL in resultJson string
                    result_json_str = task_data.get("resultJson")
                    if result_json_str:
                        try:
                            result_obj = json.loads(result_json_str)
                            urls = result_obj.get("resultUrls", [])
                            if urls:
                                return urls[0]
                        except json.JSONDecodeError:
                            pass
                    # Fallback: try common response shapes
                    output = task_data.get("output", {})
                    url = (
                        output.get("image_url")
                        or output.get("url")
                        or task_data.get("url")
                    )
                    if url:
                        return url
                    logger.error(f"Task done but no image URL: {data}")
                    return None

                if status in ("failed", "error"):
                    logger.error(f"Task failed: {data}")
                    return None

            except Exception as e:
                logger.warning(f"Poll error: {e}")

            # Exponential backoff: 2 → 3 → 4 → 6 → 8 (capped)
            interval = min(math.ceil(interval * 1.5), max_interval)

        logger.error(f"Task {task_id[:12]}... timed out after {self.POLL_TIMEOUT}s")
        return None

    def _build_prompt(self, song_title: str, mood: str, intensity: str, video_style: str = 'Thai', font_style: str = 'ลายมือพู่กัน', font_angle: str = 'เฉียงขึ้น', artist: str = '') -> str:
        """
        Build optimized prompt for Nanobanana Pro

        Prompt structure:
        [images concept & caption & title & mood: {Song} by {Artist}]
        [subject: visual representation]
        [{video_style} music video style]
        [font style + angle from user selection]
        """

        # Get font prompt from style map
        font_prompt = self.FONT_STYLES.get(font_style, self.FONT_STYLES["ลายมือพู่กัน"])

        # Add angle to font prompt
        if font_angle == "เฉียงขึ้น":
            font_prompt += ", tilted upward angle, dynamic slanted text"

        # Song title with artist
        title_part = f"{song_title} by {artist}" if artist else song_title

        # Build comprehensive prompt
        prompt = (
            f"[images concept & caption & title & mood: {title_part}]"
            f"[subject: คนที่สื่อความหมายถึงอารมณ์เพลง]"
            f"[{video_style} Music video style]"
            f"[{font_prompt}]"
        )

        return prompt

    def _download_image(
        self,
        image_url: str,
        output_path: Optional[str],
        song_title: str
    ) -> Optional[str]:
        """Download image from URL and save locally"""
        try:
            if not output_path:
                output_path = f"generated_{song_title.replace(' ', '_')}.png"

            # Create directory if needed
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Downloading image to {output_path}...")

            img_response = requests.get(image_url, timeout=60)
            if img_response.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(img_response.content)

                logger.info(f"Image saved: {output_path}")
                return output_path
            else:
                logger.error(f"Failed to download image: {img_response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    def generate_batch(
        self,
        songs: list,
        output_folder: str = './outputs'
    ) -> Dict[str, str]:
        """
        Generate images for multiple songs

        Args:
            songs: List of dicts with 'title', 'mood', 'intensity'
            output_folder: Where to save images

        Returns:
            Dict mapping song title to image path
        """
        results = {}

        for i, song_info in enumerate(songs, 1):
            logger.info(f"\n[{i}/{len(songs)}] Processing: {song_info['title']}")

            output_path = Path(output_folder) / f"{song_info['title'].replace(' ', '_')}.png"

            image_path = self.generate_album_art(
                song_title=song_info['title'],
                mood=song_info['mood'],
                intensity=song_info.get('intensity', 'medium'),
                output_path=str(output_path)
            )

            if image_path:
                results[song_info['title']] = image_path

            # Rate limit - be nice to API
            if i < len(songs):
                time.sleep(2)

        return results
