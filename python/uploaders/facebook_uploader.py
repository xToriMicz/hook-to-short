"""
Facebook Reels Uploader — Graph API
อัปโหลดวิดีโอสั้นไปยัง Facebook เป็น Reels ผ่าน Graph API

Setup:
1. ไปที่ developers.facebook.com → สร้าง App
2. เพิ่ม Facebook Login product
3. สร้าง Access Token (ใน Graph API Explorer)
   - permissions: publish_video (+ pages_manage_posts ถ้าโพสต์ลง Page)
4. แปลงเป็น Long-Lived Token (หมดอายุ 60 วัน)
5. คัดลอก Access Token มาใส่ในตั้งค่า
   - Page ID เป็น optional (ถ้าไม่ใส่จะใช้ "me" = โปรไฟล์ส่วนตัว)
"""

import os
import time
import logging
from typing import Optional, Callable

import requests

from . import UploadResult, UploadStatus, UploadRequest, ProgressFileReader

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class FacebookUploader:
    def __init__(self, page_id: str = "", access_token: str = ""):
        self.page_id = page_id.strip() or "me"
        self.access_token = access_token

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def is_authenticated(self) -> bool:
        """Verify token is valid by checking account info."""
        if not self.is_configured():
            return False
        try:
            resp = requests.get(
                f"{GRAPH_API_BASE}/{self.page_id}",
                params={"access_token": self.access_token, "fields": "name"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def upload(self, request: UploadRequest,
               progress_callback: Optional[Callable[[float], None]] = None) -> UploadResult:
        """Upload video to Facebook Page as a Reel via resumable upload."""
        if not self.is_configured():
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error="ยังไม่ได้ตั้งค่า Access Token",
            )

        if not os.path.exists(request.video_path):
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error=f"ไม่พบไฟล์วิดีโอ: {request.video_path}",
            )

        file_size = os.path.getsize(request.video_path)

        # Build description with hashtags
        description = request.title
        if request.description:
            description = f"{request.title}\n{request.description}"
        if request.tags:
            description += "\n" + " ".join(f"#{t}" for t in request.tags)

        # Step 1: Initialize upload session
        try:
            logger.info(f"Facebook: เริ่มอัปโหลด '{request.title}'...")
            init_resp = requests.post(
                f"{GRAPH_API_BASE}/{self.page_id}/video_reels",
                params={"access_token": self.access_token},
                json={
                    "upload_phase": "start",
                },
                timeout=30,
            )
            init_data = init_resp.json()

            if "video_id" not in init_data:
                error = init_data.get("error", {}).get("message", str(init_data))
                return UploadResult(
                    platform="Facebook",
                    status=UploadStatus.FAILED,
                    error=f"Init failed: {error}",
                )

            video_id = init_data["video_id"]
            upload_url = init_data.get("upload_url")

        except requests.exceptions.Timeout:
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error="หมดเวลาเชื่อมต่อ Facebook — ตรวจสอบอินเทอร์เน็ต",
            )
        except Exception as e:
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error=f"เริ่มอัปโหลดไม่สำเร็จ: {str(e)[:150]}",
            )

        # Step 2: Upload video file with progress tracking
        try:
            with open(request.video_path, "rb") as f:
                wrapped = ProgressFileReader(f, file_size, progress_callback)
                upload_resp = requests.post(
                    upload_url,
                    headers={
                        "Authorization": f"OAuth {self.access_token}",
                        "offset": "0",
                        "file_size": str(file_size),
                    },
                    data=wrapped,
                    timeout=300,
                )

            if upload_resp.status_code != 200:
                return UploadResult(
                    platform="Facebook",
                    status=UploadStatus.FAILED,
                    error=f"Upload failed: HTTP {upload_resp.status_code}",
                )

        except requests.exceptions.Timeout:
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error="อัปโหลดหมดเวลา — ไฟล์อาจใหญ่เกินไปหรือเน็ตช้า",
            )
        except Exception as e:
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error=f"อัปโหลดไม่สำเร็จ: {str(e)[:150]}",
            )

        # Step 3: Finish — publish the reel
        try:
            finish_resp = requests.post(
                f"{GRAPH_API_BASE}/{self.page_id}/video_reels",
                params={"access_token": self.access_token},
                json={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "title": request.title[:255],
                    "description": description[:5000],
                },
                timeout=30,
            )
            finish_data = finish_resp.json()

            if finish_data.get("success"):
                post_url = f"https://www.facebook.com/reel/{video_id}"
                logger.info(f"Facebook: อัปโหลดสำเร็จ — {post_url}")
                return UploadResult(
                    platform="Facebook",
                    status=UploadStatus.SUCCESS,
                    url=post_url,
                    video_id=video_id,
                )
            else:
                error = finish_data.get("error", {}).get("message", str(finish_data))
                return UploadResult(
                    platform="Facebook",
                    status=UploadStatus.FAILED,
                    error=f"Publish failed: {error}",
                )

        except Exception as e:
            return UploadResult(
                platform="Facebook",
                status=UploadStatus.FAILED,
                error=f"เผยแพร่ไม่สำเร็จ: {str(e)[:150]}",
            )
