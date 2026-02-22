"""
TikTok Uploader — Content Posting API v2
อัปโหลดวิดีโอสั้นไปยัง TikTok ผ่าน Official API

Setup:
1. ไปที่ developers.tiktok.com → สร้าง App
2. เปิด scope: video.upload, video.publish
3. ตั้ง Redirect URI: http://localhost:8585
4. คัดลอก Client Key + Client Secret มาใส่ในตั้งค่า
"""

import os
import json
import time
import logging
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional, Callable

import requests

from . import UploadResult, UploadStatus, UploadRequest, ProgressFileReader

logger = logging.getLogger(__name__)

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_PUBLISH_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_TOKEN_FILE = "tiktok_token.json"
REDIRECT_PORT = 8585
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Temporary HTTP handler to capture OAuth callback."""
    auth_code = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h2>TikTok เชื่อมต่อสำเร็จ!</h2>"
                "<p>ปิดหน้านี้แล้วกลับไปที่ Hook-to-Short ได้เลย</p>"
                "</body></html>".encode("utf-8")
            )
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>ผิดพลาด: {error}</h2></body></html>".encode("utf-8"))
        # Shutdown server after handling
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        pass  # Suppress HTTP server logs


class TikTokUploader:
    def __init__(self, client_key: str = "", client_secret: str = "",
                 token_path: str = TIKTOK_TOKEN_FILE):
        self.client_key = client_key
        self.client_secret = client_secret
        self.token_path = token_path
        self.access_token = None
        self._load_token()

    def _load_token(self):
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r") as f:
                    data = json.load(f)
                self.access_token = data.get("access_token")
                expires_at = data.get("expires_at", 0)
                if time.time() > expires_at:
                    # Token expired — try refresh
                    refresh_token = data.get("refresh_token")
                    if refresh_token:
                        self._refresh_token(refresh_token)
                    else:
                        self.access_token = None
            except Exception:
                self.access_token = None

    def _save_token(self, token_data: dict):
        save_data = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": time.time() + token_data.get("expires_in", 86400),
        }
        with open(self.token_path, "w") as f:
            json.dump(save_data, f, indent=2)
        self.access_token = save_data["access_token"]

    def _refresh_token(self, refresh_token: str) -> bool:
        try:
            resp = requests.post(TIKTOK_TOKEN_URL, json={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }, timeout=30)
            data = resp.json()
            if "access_token" in data:
                self._save_token(data)
                return True
        except Exception as e:
            logger.warning(f"TikTok token refresh failed: {e}")
        self.access_token = None
        return False

    def is_configured(self) -> bool:
        return bool(self.client_key and self.client_secret)

    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    def authenticate(self) -> bool:
        """Run OAuth2 flow — opens browser for TikTok authorization."""
        if not self.is_configured():
            logger.error("TikTok: ยังไม่ได้ตั้งค่า Client Key / Client Secret")
            return False

        # Build authorization URL
        params = {
            "client_key": self.client_key,
            "scope": "video.upload,video.publish",
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": "hookshort",
        }
        auth_url = f"{TIKTOK_AUTH_URL}?{urlencode(params)}"

        # Start local server
        _OAuthCallbackHandler.auth_code = None
        server = HTTPServer(("localhost", REDIRECT_PORT), _OAuthCallbackHandler)

        logger.info("TikTok: เปิดเบราว์เซอร์เพื่ออนุญาต...")
        webbrowser.open(auth_url)

        # Wait for callback (timeout 120s)
        server.timeout = 120
        server.handle_request()
        server.server_close()

        if not _OAuthCallbackHandler.auth_code:
            logger.error("TikTok: ไม่ได้รับ authorization code")
            return False

        # Exchange code for token
        try:
            resp = requests.post(TIKTOK_TOKEN_URL, json={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "code": _OAuthCallbackHandler.auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            }, timeout=30)
            data = resp.json()

            if "access_token" in data:
                self._save_token(data)
                logger.info("TikTok: เชื่อมต่อสำเร็จ")
                return True
            else:
                error = data.get("error", {}).get("message", str(data))
                logger.error(f"TikTok: token exchange failed — {error}")
                return False

        except Exception as e:
            logger.error(f"TikTok: authentication error — {e}")
            return False

    def upload(self, request: UploadRequest,
               progress_callback: Optional[Callable[[float], None]] = None) -> UploadResult:
        """Upload video to TikTok via Content Posting API."""
        if not self.access_token:
            if not self.authenticate():
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error="ยังไม่ได้เชื่อมต่อ TikTok — ตั้งค่า OAuth ก่อน",
                )

        if not os.path.exists(request.video_path):
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error=f"ไม่พบไฟล์วิดีโอ: {request.video_path}",
            )

        file_size = os.path.getsize(request.video_path)

        # Build caption with hashtags
        caption = request.title
        if request.description:
            caption = f"{request.title} {request.description}"
        if request.tags:
            caption += " " + " ".join(f"#{t}" for t in request.tags)

        # Map privacy
        privacy_map = {
            "public": "PUBLIC_TO_EVERYONE",
            "private": "SELF_ONLY",
            "unlisted": "MUTUAL_FOLLOW_FRIENDS",
        }
        privacy_level = privacy_map.get(request.privacy, "PUBLIC_TO_EVERYONE")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        # Step 1: Initialize upload
        try:
            logger.info(f"TikTok: เริ่มอัปโหลด '{request.title}'...")
            init_body = {
                "post_info": {
                    "title": caption[:150],
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": file_size,  # Single chunk for small files
                    "total_chunk_count": 1,
                },
            }
            resp = requests.post(TIKTOK_PUBLISH_URL, json=init_body,
                                 headers=headers, timeout=30)
            data = resp.json()

            if data.get("error", {}).get("code") != "ok":
                error = data.get("error", {}).get("message", str(data))
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error=f"Init failed: {error}",
                )

            publish_id = data["data"]["publish_id"]
            upload_url = data["data"]["upload_url"]

        except requests.exceptions.Timeout:
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error="หมดเวลาเชื่อมต่อ TikTok — ตรวจสอบอินเทอร์เน็ต",
            )
        except Exception as e:
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error=f"เริ่มอัปโหลดไม่สำเร็จ: {str(e)[:150]}",
            )

        # Step 2: Upload video file with progress tracking
        try:
            upload_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            }
            with open(request.video_path, "rb") as f:
                wrapped = ProgressFileReader(f, file_size, progress_callback)
                resp = requests.put(upload_url, data=wrapped,
                                    headers=upload_headers, timeout=300)

            if resp.status_code not in (200, 201):
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error=f"Upload failed: HTTP {resp.status_code}",
                )

        except requests.exceptions.Timeout:
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error="อัปโหลดหมดเวลา — ไฟล์อาจใหญ่เกินไปหรือเน็ตช้า",
            )
        except Exception as e:
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error=f"อัปโหลดไม่สำเร็จ: {str(e)[:150]}",
            )

        # Step 3: Check publish status (poll)
        try:
            for _ in range(30):  # Max 5 minutes (10s intervals)
                time.sleep(10)
                status_resp = requests.post(
                    TIKTOK_STATUS_URL,
                    json={"publish_id": publish_id},
                    headers=headers,
                    timeout=30,
                )
                status_data = status_resp.json()
                pub_status = status_data.get("data", {}).get("status", "")

                if pub_status == "PUBLISH_COMPLETE":
                    logger.info("TikTok: อัปโหลดสำเร็จ")
                    return UploadResult(
                        platform="TikTok",
                        status=UploadStatus.SUCCESS,
                        video_id=publish_id,
                    )
                elif pub_status in ("FAILED", "PUBLISH_FAILED"):
                    fail_reason = status_data.get("data", {}).get("fail_reason", "unknown")
                    return UploadResult(
                        platform="TikTok",
                        status=UploadStatus.FAILED,
                        error=f"Publish failed: {fail_reason}",
                    )
                # Still processing — continue polling

            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error="Publish timeout (5 นาที)",
            )

        except Exception as e:
            # Upload succeeded but status check failed — treat as partial success
            logger.warning(f"TikTok: status check error — {e}")
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.SUCCESS,
                video_id=publish_id,
                error=f"อัปโหลดแล้ว แต่ตรวจสถานะไม่ได้: {e}",
            )
