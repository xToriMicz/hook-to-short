"""
YouTube Shorts Uploader — Google API OAuth2
อัปโหลดวิดีโอสั้นไปยัง YouTube Shorts ผ่าน YouTube Data API v3

Setup:
1. ไปที่ Google Cloud Console (console.cloud.google.com)
2. สร้าง Project → เปิด YouTube Data API v3
3. สร้าง OAuth 2.0 Client ID (Desktop App)
4. ดาวน์โหลด client_secrets.json → วางใน project folder
"""

import os
import json
import logging
from typing import Optional, Callable

from . import UploadResult, UploadStatus, UploadRequest

logger = logging.getLogger(__name__)

# Default paths
CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    def __init__(self, client_secrets_path: str = CLIENT_SECRETS_FILE,
                 token_path: str = TOKEN_FILE):
        self.client_secrets_path = client_secrets_path
        self.token_path = token_path
        self.service = None

    def is_configured(self) -> bool:
        """Check if client_secrets.json exists."""
        return os.path.exists(self.client_secrets_path)

    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        if not os.path.exists(self.token_path):
            return False
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            return creds and creds.valid
        except Exception:
            return False

    def authenticate(self) -> bool:
        """Run OAuth2 flow — opens browser for consent on first use."""
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            logger.error("ต้องติดตั้ง: pip install google-api-python-client google-auth-oauthlib")
            return False

        if not self.is_configured():
            logger.error(f"ไม่พบไฟล์ {self.client_secrets_path} — ดาวน์โหลดจาก Google Cloud Console")
            return False

        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_path, SCOPES)
                creds = flow.run_local_server(port=0)

            # Save token
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())

        self.service = build("youtube", "v3", credentials=creds)
        logger.info("YouTube: เชื่อมต่อสำเร็จ")
        return True

    def upload(self, request: UploadRequest,
               progress_callback: Optional[Callable[[float], None]] = None) -> UploadResult:
        """Upload video to YouTube as a Short."""
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            return UploadResult(
                platform="YouTube",
                status=UploadStatus.FAILED,
                error="ต้องติดตั้ง google-api-python-client",
            )

        if not self.service:
            if not self.authenticate():
                return UploadResult(
                    platform="YouTube",
                    status=UploadStatus.FAILED,
                    error="ยังไม่ได้เชื่อมต่อ YouTube — ตั้งค่า OAuth ก่อน",
                )

        if not os.path.exists(request.video_path):
            return UploadResult(
                platform="YouTube",
                status=UploadStatus.FAILED,
                error=f"ไม่พบไฟล์วิดีโอ: {request.video_path}",
            )

        # Build title with #Shorts tag
        title = request.title
        if "#Shorts" not in title:
            title = f"{title} #Shorts"

        # Build description with hashtags
        description = request.description or title
        if request.tags:
            tag_str = " ".join(f"#{t}" for t in request.tags)
            description = f"{description}\n\n{tag_str}"
        if "#Shorts" not in description:
            description += "\n#Shorts"

        body = {
            "snippet": {
                "title": title[:100],  # YouTube max 100 chars
                "description": description[:5000],
                "tags": request.tags or [],
                "categoryId": "10",  # Music
            },
            "status": {
                "privacyStatus": request.privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            request.video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5,  # 5MB chunks
        )

        try:
            logger.info(f"YouTube: เริ่มอัปโหลด '{title}'...")
            insert_request = self.service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status and progress_callback:
                    progress_callback(status.progress())

            video_id = response.get("id", "")
            video_url = f"https://youtube.com/shorts/{video_id}"

            logger.info(f"YouTube: อัปโหลดสำเร็จ — {video_url}")
            return UploadResult(
                platform="YouTube",
                status=UploadStatus.SUCCESS,
                url=video_url,
                video_id=video_id,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"YouTube: อัปโหลดไม่สำเร็จ — {error_msg}")
            # Translate common errors
            if "quota" in error_msg.lower():
                friendly = "YouTube API quota หมด — ลองอีกครั้งพรุ่งนี้"
            elif "forbidden" in error_msg.lower() or "403" in error_msg:
                friendly = "ไม่มีสิทธิ์อัปโหลด — ตรวจสอบ OAuth scope"
            elif "notFound" in error_msg or "404" in error_msg:
                friendly = "ไม่พบ channel — ตรวจสอบ account"
            elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                friendly = "หมดเวลาเชื่อมต่อ — ตรวจสอบอินเทอร์เน็ต"
            else:
                friendly = error_msg[:200]
            return UploadResult(
                platform="YouTube",
                status=UploadStatus.FAILED,
                error=friendly,
            )
