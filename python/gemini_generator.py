"""
Gemini Image Generation — Fallback for Kie.ai
Uses Gemini 3 Pro Image (Nano Banana Pro) to generate album art when Kie.ai is unavailable.
Only Gemini 3 Pro can render text in images.
"""

import os
import base64
import logging
import requests
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GeminiImageGenerator:
    """Generate images using Google Gemini 3 Pro Image API (Nano Banana Pro)"""

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            logger.error("Gemini API key not configured — set GEMINI_API_KEY in .env")

    # Same font style map as KieAIGenerator — same model (Nano Banana Pro)
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
        custom_prompt: str = '',
    ) -> Optional[str]:
        """
        Generate album art image using Gemini 3 Pro Image.
        Same interface as KieAIGenerator.generate_album_art().

        Returns:
            Path to generated image or None if failed
        """
        if not self.api_key:
            logger.error("Gemini API key not set")
            return None

        try:
            logger.info(f"[Gemini] Generating album art for: {song_title} by {artist}")

            prompt = custom_prompt or self._build_prompt(song_title, mood, intensity, video_style, font_style, font_angle, artist)

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {
                        "aspectRatio": "9:16"
                    }
                }
            }

            url = f"{self.API_URL}?key={self.api_key}"

            logger.info("[Gemini] Sending request...")
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120,
            )

            if response.status_code != 200:
                logger.error(f"[Gemini] API Error {response.status_code}: {response.text[:500]}")
                return None

            result = response.json()
            return self._extract_and_save_image(result, output_path, song_title)

        except Exception as e:
            logger.error(f"[Gemini] Error generating album art: {e}")
            return None

    def _build_prompt(self, song_title: str, mood: str, intensity: str, video_style: str = 'Thai', font_style: str = 'ลายมือพู่กัน', font_angle: str = 'เฉียงขึ้น', artist: str = '') -> str:
        """Build prompt for Nano Banana Pro — same format as KieAIGenerator"""
        font_prompt = self.FONT_STYLES.get(font_style, self.FONT_STYLES["ลายมือพู่กัน"])

        if font_angle == "เฉียงขึ้น":
            font_prompt += ", tilted upward angle, dynamic slanted text"

        title_part = f"{song_title} by {artist}" if artist else song_title

        prompt = (
            f"[images concept & caption & title & mood: {title_part}]"
            f"[subject: คนที่สื่อความหมายถึงอารมณ์เพลง]"
            f"[{video_style} Music video style]"
            f"[{font_prompt}]"
        )

        return prompt

    def _extract_and_save_image(self, result: dict, output_path: Optional[str], song_title: str) -> Optional[str]:
        """Extract base64 image from Gemini response and save as PNG"""
        try:
            candidates = result.get("candidates", [])
            if not candidates:
                logger.error("[Gemini] No candidates in response")
                return None

            parts = candidates[0].get("content", {}).get("parts", [])

            for part in parts:
                inline_data = part.get("inlineData")
                if inline_data and inline_data.get("data"):
                    image_bytes = base64.b64decode(inline_data["data"])

                    if not output_path:
                        output_path = f"generated_{song_title.replace(' ', '_')}.png"

                    output_file = Path(output_path)
                    output_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(output_path, 'wb') as f:
                        f.write(image_bytes)

                    logger.info(f"[Gemini] Image saved: {output_path}")
                    return output_path

            logger.error(f"[Gemini] No image data in response parts: {[list(p.keys()) for p in parts]}")
            return None

        except Exception as e:
            logger.error(f"[Gemini] Error extracting image: {e}")
            return None
