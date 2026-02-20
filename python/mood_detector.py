"""
YouTube metadata extraction and mood detection
"""

import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Mood mapping from song keywords
MOOD_KEYWORDS = {
    'happy': ['happy', 'joy', 'love', 'beautiful', 'smile', 'party', 'fun', 'dance', 'uplifting'],
    'sad': ['sad', 'cry', 'pain', 'heartbreak', 'loss', 'goodbye', 'lonely', 'tear', 'broken'],
    'energetic': ['energy', 'power', 'strong', 'epic', 'intense', 'explosive', 'electric', 'rock', 'metal'],
    'calm': ['calm', 'relax', 'peace', 'quiet', 'soft', 'gentle', 'sleep', 'meditate', 'ambient'],
    'romantic': ['love', 'romantic', 'heart', 'kiss', 'sweet', 'dream', 'forever', 'passion'],
    'angry': ['angry', 'rage', 'dark', 'aggressive', 'fight', 'rebel', 'scream', 'violent'],
}

class MoodDetector:
    """Detect mood from song title and metadata"""
    
    def __init__(self):
        self.mood_map = MOOD_KEYWORDS
        self.default_mood = 'calm'
    
    def detect_from_title(self, title: str) -> str:
        """Detect mood from song title"""
        title_lower = title.lower()
        
        # Count matches for each mood
        mood_scores = {}
        for mood, keywords in self.mood_map.items():
            score = sum(1 for keyword in keywords if keyword in title_lower)
            if score > 0:
                mood_scores[mood] = score
        
        if mood_scores:
            return max(mood_scores, key=mood_scores.get)
        
        return self.default_mood
    
    def detect_from_artist_title(self, artist: str, title: str) -> Dict[str, str]:
        """
        Detect mood from artist + title
        Returns: {mood, intensity, vibe}
        """
        full_text = f"{artist} {title}".lower()
        
        mood = self.detect_from_title(title)
        
        # Detect intensity
        intensity = 'medium'
        intense_keywords = ['epic', 'extreme', 'ultimate', 'super', 'ultra']
        if any(kw in full_text for kw in intense_keywords):
            intensity = 'high'
        elif any(kw in full_text for kw in ['subtle', 'light', 'soft', 'quiet']):
            intensity = 'low'
        
        # Detect vibe
        vibe = 'studio'
        if any(kw in full_text for kw in ['live', 'concert', 'performance']):
            vibe = 'live'
        elif any(kw in full_text for kw in ['remix', 'cover', 'version']):
            vibe = 'remix'
        
        return {
            'mood': mood,
            'intensity': intensity,
            'vibe': vibe,
        }
    
    def get_mood_description(self, mood: str) -> Dict[str, str]:
        """Get Thai description for mood"""
        mood_descriptions = {
            'happy': {
                'emotion': 'ความสุข',
                'color': '#FFD700',  # Gold
                'energy': 'สูง',
                'style': 'สดใส, ชีวชีวะ'
            },
            'sad': {
                'emotion': 'ความเศร้า',
                'color': '#4169E1',  # Royal Blue
                'energy': 'ต่ำ',
                'style': 'เศร้าสลึง, ลึกลับ'
            },
            'energetic': {
                'emotion': 'พลังแรง',
                'color': '#FF4500',  # Orange Red
                'energy': 'สูงมาก',
                'style': 'แรงกล้า, ระเบิด'
            },
            'calm': {
                'emotion': 'ความสงบ',
                'color': '#87CEEB',  # Sky Blue
                'energy': 'ต่ำ',
                'style': 'นิ่ง, สงบสุข'
            },
            'romantic': {
                'emotion': 'ความรักหวัน',
                'color': '#FF1493',  # Deep Pink
                'energy': 'ปานกลาง',
                'style': 'หวาน, หวังใจ'
            },
            'angry': {
                'emotion': 'ความโกรธ',
                'color': '#DC143C',  # Crimson
                'energy': 'สูงมาก',
                'style': 'ดุดัน, ขุ่นเคือง'
            },
        }
        
        return mood_descriptions.get(mood, mood_descriptions['calm'])


def extract_metadata_from_title(title: str) -> Dict[str, str]:
    """
    Extract song info from YouTube title
    Handle patterns like: "Song Name - Artist" or "Artist - Song Name"
    """
    # Try to split by dash
    if ' - ' in title:
        parts = title.split(' - ', 1)
        # Heuristic: longer part is usually song name
        return {
            'artist': parts[0].strip(),
            'song': parts[1].strip(),
        }
    
    # Try to split by '|'
    if ' | ' in title:
        parts = title.split(' | ', 1)
        return {
            'artist': parts[0].strip(),
            'song': parts[1].strip(),
        }
    
    # Can't split - use whole as song name
    return {
        'artist': 'Unknown Artist',
        'song': title.strip(),
    }


if __name__ == '__main__':
    detector = MoodDetector()
    
    # Test
    test_titles = [
        "Happy Days - Artist",
        "Broken Heart - Sad Song",
        "Epic Battle - Rock Band",
        "Peaceful Night - Ambient Music",
    ]
    
    for title in test_titles:
        metadata = extract_metadata_from_title(title)
        mood_info = detector.detect_from_artist_title(
            metadata['artist'],
            metadata['song']
        )
        print(f"Title: {title}")
        print(f"  Mood: {mood_info['mood']} ({mood_info['intensity']})")
        print()
