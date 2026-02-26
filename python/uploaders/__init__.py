"""
Hook-to-Short — Social Media Uploaders
อัปโหลดวิดีโอสั้นไปยัง YouTube, TikTok, Facebook
"""

import os
import time
import random as _random
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    publish_at: Optional[str] = None  # ISO 8601 datetime for scheduling


# ---------------------------------------------------------------------------
# Scheduling — optimal posting times per platform (ICT, UTC+7)
# ---------------------------------------------------------------------------

# Peak engagement hour ranges (start, end_exclusive) in local time
PEAK_HOURS: dict[str, list[tuple[int, int]]] = {
    "youtube":  [(12, 15), (19, 21)],
    "tiktok":   [(11, 13), (19, 22)],
    "facebook": [(12, 14), (18, 20)],
}

# Publish mode labels → days offset (None = not scheduled)
PUBLISH_MODES: dict[str, Optional[int]] = {
    "โพสทันที":        None,
    "ส่วนตัว":         None,
    "ไม่แสดง":         None,
    "ตั้งเวลา +1 วัน":  1,
    "ตั้งเวลา +2 วัน":  2,
    "ตั้งเวลา +3 วัน":  3,
    "สุ่ม 1-3 วัน":     -1,   # sentinel: random 1-3
}


def calculate_publish_time(platform: str, days_offset: int) -> str:
    """Calculate optimal publish time for a platform.

    Returns ISO 8601 datetime string with timezone (ICT +07:00).
    Picks a random hour from the platform's peak engagement windows.
    """
    ict = timezone(timedelta(hours=7))
    now = datetime.now(ict)
    target_date = now + timedelta(days=days_offset)

    ranges = PEAK_HOURS.get(platform, [(12, 15), (19, 21)])
    start_h, end_h = _random.choice(ranges)
    hour = _random.randint(start_h, end_h - 1)
    minute = _random.choice([0, 15, 30, 45])

    publish_time = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return publish_time.isoformat()


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


class ProgressFileReader:
    """Wraps a file object to report read progress via callback.

    Usage with requests:
        with open(path, "rb") as f:
            wrapped = ProgressFileReader(f, file_size, callback)
            requests.put(url, data=wrapped)
    """

    def __init__(self, file_obj, total_size: int,
                 callback: Optional[Callable[[float], None]] = None):
        self._file = file_obj
        self._total = total_size
        self._read_so_far = 0
        self._callback = callback

    def read(self, size: int = -1) -> bytes:
        data = self._file.read(size)
        if data:
            self._read_so_far += len(data)
            if self._callback and self._total > 0:
                self._callback(min(self._read_so_far / self._total, 1.0))
        return data

    def __len__(self) -> int:
        return self._total


def get_output_videos(outputs_folder: str = "./outputs") -> list[dict]:
    """Scan outputs folder for completed .mp4 videos (newest first)."""
    videos = []
    if not os.path.isdir(outputs_folder):
        return videos
    for fname in os.listdir(outputs_folder):
        if fname.lower().endswith(".mp4"):
            fpath = os.path.join(outputs_folder, fname)
            stat = os.stat(fpath)
            size_mb = stat.st_size / (1024 * 1024)
            mtime = stat.st_mtime
            videos.append({
                "filename": fname,
                "path": fpath,
                "size_mb": round(size_mb, 2),
                "title": fname.replace("_short.mp4", "").replace("_", " "),
                "mtime": mtime,
                "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
            })
    videos.sort(key=lambda v: v["mtime"], reverse=True)
    return videos
