"""
Hook-to-Short — Social Media Uploaders
อัปโหลดวิดีโอสั้นไปยัง YouTube, TikTok, Facebook
"""

import os
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAYS = [5, 15]  # seconds between retries


class UploadStatus(Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class UploadResult:
    platform: str
    status: UploadStatus
    url: Optional[str] = None
    video_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class UploadRequest:
    """All info needed to upload a video to any platform."""
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    privacy: str = "public"  # public, private, unlisted


def upload_with_retry(upload_fn: Callable[[], UploadResult],
                      max_retries: int = MAX_RETRIES) -> UploadResult:
    """Retry an upload function on failure with exponential backoff."""
    last_result = None
    for attempt in range(1 + max_retries):
        result = upload_fn()
        if result.status == UploadStatus.SUCCESS:
            return result
        last_result = result
        if attempt < max_retries:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            logger.info(f"{result.platform}: ลองใหม่ครั้งที่ {attempt + 1} (รอ {delay} วินาที)...")
            time.sleep(delay)
    return last_result


def get_output_videos(outputs_folder: str = "./outputs") -> list[dict]:
    """Scan outputs folder for completed .mp4 videos."""
    videos = []
    if not os.path.isdir(outputs_folder):
        return videos
    for fname in sorted(os.listdir(outputs_folder)):
        if fname.lower().endswith(".mp4"):
            fpath = os.path.join(outputs_folder, fname)
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
            videos.append({
                "filename": fname,
                "path": fpath,
                "size_mb": round(size_mb, 2),
                "title": fname.replace("_short.mp4", "").replace("_", " "),
            })
    return videos
