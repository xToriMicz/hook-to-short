"""
Hook-to-Short — CustomTkinter Desktop UI
ดาวน์โหลดเพลงจาก YouTube, ตัดท่อนฮุก, ตรวจอารมณ์, สร้างภาพปก, ตัดต่อวิดีโอสั้น
"""

import os
import sys
import json
import logging
import subprocess
import re
from urllib.parse import urlparse, parse_qs
import threading
import time
import warnings
import webbrowser
import glob as glob_mod
from pathlib import Path
from datetime import datetime
from typing import Optional

# Suppress librosa/soundfile warnings
warnings.filterwarnings("ignore", message="PySoundFile failed")
warnings.filterwarnings("ignore", category=FutureWarning, module="librosa")

# Load .env file (PyInstaller: look next to the .exe, not in _MEIPASS)
if getattr(sys, 'frozen', False):
    _base_dir = os.path.dirname(sys.executable)
else:
    _base_dir = os.path.dirname(__file__)
_env_path = os.path.join(_base_dir, ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

import customtkinter as ctk
import tkinter.font as tkfont
import tkinter.filedialog as tkfiledialog
import tkinter.messagebox as tkmessagebox
from PIL import Image as PILImage

# Monkey-patch: soundfile 0.13+ removed SoundFileRuntimeError but librosa still expects it
import soundfile as _sf
if not hasattr(_sf, 'SoundFileRuntimeError'):
    _sf.SoundFileRuntimeError = RuntimeError

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from python.mood_detector import MoodDetector, extract_metadata_from_title
from python.kie_generator import KieAIGenerator
from python.gemini_generator import GeminiImageGenerator
from python.video_composer import VideoComposer, compose_complete_short
from python.uploaders import (
    UploadRequest, UploadResult, UploadStatus, get_output_videos, upload_with_retry,
    PUBLISH_MODES, calculate_publish_time,
)
from python.uploaders.youtube_uploader import YouTubeUploader
from python.uploaders.tiktok_browser import TikTokBrowserUploader
from python.uploaders.facebook_uploader import FacebookUploader

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DOWNLOADS_FOLDER = "./downloads"
OUTPUTS_FOLDER = "./outputs"
TRACKS_DB = "tracks.json"
SETTINGS_FILE = "settings.json"
UPLOAD_HISTORY_FILE = "upload_history.json"

os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)
os.makedirs(OUTPUTS_FOLDER, exist_ok=True)

LOG_FILE = os.path.join(OUTPUTS_FOLDER, "hook-to-short.log")
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w")
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
_file_handler.setLevel(logging.DEBUG)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        _file_handler,
    ],
    force=True,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Track persistence (same format as app.py)
# ---------------------------------------------------------------------------

def load_tracks() -> list:
    if os.path.exists(TRACKS_DB):
        with open(TRACKS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_tracks(tracks: list):
    with open(TRACKS_DB, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)


def add_track(track_info: dict) -> dict:
    tracks = load_tracks()
    track_info["id"] = len(tracks) + 1
    track_info["created_at"] = datetime.now().isoformat()
    track_info["status"] = "completed"
    tracks.append(track_info)
    save_tracks(tracks)
    return track_info


def sync_tracks_with_folder():
    """Sync tracks.json with actual MP3 files in the downloads folder.

    - New MP3 files found on disk → added to tracks.json automatically
    - Tracked files that no longer exist → removed from tracks.json
    - Existing files whose name changed externally → title updated
    """
    tracks = load_tracks()
    mp3_files = glob_mod.glob(os.path.join(DOWNLOADS_FOLDER, "*.mp3"))
    mp3_norm_set = {os.path.normpath(f) for f in mp3_files}
    tracked_norm_set = {os.path.normpath(t.get("file_path", "")) for t in tracks}

    changed = False

    # Keep only tracks whose files still exist on disk
    surviving = []
    for t in tracks:
        norm = os.path.normpath(t.get("file_path", ""))
        if norm in mp3_norm_set:
            # Update title/filename if file was renamed externally
            current_stem = Path(norm).stem
            if t.get("title") != current_stem:
                t["title"] = current_stem
                t["filename"] = os.path.basename(norm)
                t["file_path"] = os.path.join(DOWNLOADS_FOLDER, os.path.basename(norm))
                changed = True
            surviving.append(t)
        else:
            changed = True  # file gone → drop track

    # Add new MP3 files not yet tracked
    max_id = max((t.get("id", 0) for t in surviving), default=0)
    for mp3_path in mp3_files:
        norm = os.path.normpath(mp3_path)
        if norm not in tracked_norm_set:
            max_id += 1
            file_size = os.path.getsize(mp3_path) / (1024 * 1024)
            surviving.append({
                "id": max_id,
                "title": Path(mp3_path).stem,
                "youtube_url": "",
                "file_path": mp3_path,
                "filename": os.path.basename(mp3_path),
                "file_size_mb": round(file_size, 2),
                "artist": "ไม่ทราบ",
                "duration": "0:00",
                "created_at": datetime.now().isoformat(),
                "status": "completed",
            })
            changed = True

    if changed:
        save_tracks(surviving)

    return surviving


def _cleanup_temp_hooks():
    """Remove leftover _tmp_hook_*.wav files from outputs."""
    for f in glob_mod.glob(os.path.join(OUTPUTS_FOLDER, "_tmp_hook_*.wav")):
        try:
            os.remove(f)
            logger.info(f"Cleaned up temp file: {os.path.basename(f)}")
        except OSError:
            pass


def _cleanup_temp_folders():
    """Remove leftover temp_* directories from downloads."""
    import shutil
    for d in glob_mod.glob(os.path.join(DOWNLOADS_FOLDER, "temp_*")):
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                logger.info(f"Cleaned up temp folder: {os.path.basename(d)}")
            except OSError:
                pass


def load_upload_history() -> list:
    if os.path.exists(UPLOAD_HISTORY_FILE):
        try:
            with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_upload_history(history: list):
    with open(UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_upload_record(video_filename: str, results: list):
    """Save upload results to history."""
    history = load_upload_history()
    for r in results:
        history.append({
            "timestamp": datetime.now().isoformat(),
            "video": video_filename,
            "platform": r.platform,
            "status": r.status.value,
            "url": r.url or "",
            "error": r.error or "",
        })
    save_upload_history(history)


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class HookToShortApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Clean up leftover temp files on startup
        _cleanup_temp_hooks()
        _cleanup_temp_folders()

        self.title("Hook-to-Short")
        self.geometry("780x750")
        self.minsize(700, 650)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # --- Thai-compatible font ---
        _preferred = ("Leelawadee UI", "Tahoma")
        _available = set(tkfont.families())
        self._thai_family = next((f for f in _preferred if f in _available), None)
        if self._thai_family:
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                         "TkHeadingFont", "TkCaptionFont", "TkTooltipFont"):
                try:
                    fobj = tkfont.nametofont(name)
                    fobj.configure(family=self._thai_family)
                except Exception:
                    pass

        def _font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
            return ctk.CTkFont(family=self._thai_family, size=size, weight=weight)

        self._font = _font

        # --- Header ---
        header = ctk.CTkLabel(self, text="Hook-to-Short", font=self._font(22, "bold"))
        header.pack(pady=(12, 0))

        # --- Tabs ---
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=14, pady=(6, 0))
        # Apply Thai font to tab header buttons
        self.tabview._segmented_button.configure(font=self._font(14))

        self.tab_download = self.tabview.add("ดาวน์โหลด")
        self.tab_library = self.tabview.add("คลังเพลง")
        self.tab_create = self.tabview.add("สร้างวิดีโอสั้น")
        self.tab_upload = self.tabview.add("อัปโหลด")
        self.tab_settings = self.tabview.add("ตั้งค่า")

        self.auto_upload_var = ctk.BooleanVar(value=False)

        self._build_download_tab()
        self._build_library_tab()
        self._build_create_tab()
        self._build_upload_tab()
        self._build_settings_tab()

        # --- Load saved settings ---
        self._load_user_settings()

        # --- Save settings on close ---
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Status bar ---
        self.status_var = ctk.StringVar(value="พร้อมใช้งาน")
        status_bar = ctk.CTkLabel(self, textvariable=self.status_var, font=self._font(12), anchor="w")
        status_bar.pack(fill="x", padx=14, pady=(2, 4))

        # --- Log panel ---
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=14)
        ctk.CTkLabel(log_header, text="Log", font=self._font(12, "bold")).pack(side="left")
        ctk.CTkButton(log_header, text="ล้าง", width=50, height=22, font=self._font(11),
                       command=self._clear_log).pack(side="right")

        self.log_box = ctk.CTkTextbox(self, height=120, font=self._font(11),
                                       state="disabled", wrap="word")
        self.log_box.pack(fill="x", padx=14, pady=(2, 8))

        # Redirect Python logging into the log panel
        self._setup_log_handler()

    # -----------------------------------------------------------------------
    # Log helpers
    # -----------------------------------------------------------------------

    def _setup_log_handler(self):
        """Route all Python logging to the UI log panel."""
        class _TkHandler(logging.Handler):
            def __init__(self, app):
                super().__init__()
                self.app = app
            def emit(self, record):
                msg = self.format(record)
                self.app.after(0, lambda m=msg: self.app._append_log(m))

        handler = _TkHandler(self)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(handler)

    def _append_log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Settings Persistence
    # -----------------------------------------------------------------------

    def _load_user_settings(self):
        s = load_settings()
        if not s:
            return
        # Download tab
        if "scan_limit" in s:
            self.scan_limit_var.set(s["scan_limit"])
        # Create Short tab
        if "hook_length" in s:
            self.hook_length_var.set(s["hook_length"])
        if "video_style" in s:
            self.style_var.set(s["video_style"])
        if "platform" in s:
            self.platform_var.set(s["platform"])
        if "font_style" in s:
            self.font_style_var.set(s["font_style"])
        if "font_angle" in s:
            self.font_angle_var.set(s["font_angle"])
        # Upload tab
        if "upload_tags" in s:
            self.upload_tags_var.set(s["upload_tags"])
        if "upload_privacy" in s:
            saved = s["upload_privacy"]
            # Migrate old values (public/private/unlisted) to new labels
            migrate = {"public": "โพสทันที", "private": "ส่วนตัว", "unlisted": "ไม่แสดง"}
            self.upload_privacy_var.set(migrate.get(saved, saved))
        if "auto_upload" in s:
            self.auto_upload_var.set(s["auto_upload"])
        if "gemini_only" in s:
            self.gemini_only_var.set(s["gemini_only"])

    def _save_user_settings(self):
        s = load_settings()  # Preserve upload credentials
        s.update({
            "scan_limit": self.scan_limit_var.get(),
            "hook_length": self.hook_length_var.get(),
            "video_style": self.style_var.get(),
            "platform": self.platform_var.get(),
            "font_style": self.font_style_var.get(),
            "font_angle": self.font_angle_var.get(),
            "upload_tags": self.upload_tags_var.get(),
            "upload_privacy": self.upload_privacy_var.get(),
            "auto_upload": self.auto_upload_var.get(),
            "gemini_only": self.gemini_only_var.get(),
        })
        save_settings(s)

    def _on_close(self):
        self._save_user_settings()
        self.destroy()

    # -----------------------------------------------------------------------
    # Download Tab
    # -----------------------------------------------------------------------

    def _build_download_tab(self):
        tab = self.tab_download

        url_frame = ctk.CTkFrame(tab, fg_color="transparent")
        url_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(url_frame, text="ลิงก์ YouTube:", font=self._font(13)).pack(side="left", padx=(0, 6))

        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="วางลิงก์ YouTube ที่นี่...", width=420, font=self._font(13))
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.url_entry.bind("<Return>", lambda _: self._on_download())

        self.download_btn = ctk.CTkButton(url_frame, text="ดาวน์โหลด", width=120, font=self._font(13), command=self._on_download)
        self.download_btn.pack(side="right")

        self.dl_progress = ctk.CTkLabel(tab, text="", font=self._font(13))
        self.dl_progress.pack(anchor="w", padx=8, pady=(4, 2))

        self.dl_result_frame = ctk.CTkFrame(tab)
        self.dl_result_frame.pack(fill="x", padx=8, pady=4)
        self.dl_result_label = ctk.CTkLabel(self.dl_result_frame, text="", justify="left", anchor="w", font=self._font(13))
        self.dl_result_label.pack(fill="x", padx=8, pady=6)
        self.dl_result_frame.pack_forget()

        # --- Channel Scanner ---
        sep_label = ctk.CTkLabel(tab, text="── สแกน ช่อง / Playlist / Releases ──", font=self._font(13),
                                  text_color="gray")
        sep_label.pack(pady=(12, 4))

        ch_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ch_frame.pack(fill="x", padx=8, pady=(0, 4))

        ctk.CTkLabel(ch_frame, text="ลิงก์สแกน:", font=self._font(13)).pack(side="left", padx=(0, 6))
        self.channel_url_entry = ctk.CTkEntry(ch_frame, placeholder_text="วางลิงก์ช่อง / playlist / releases ...",
                                               width=400, font=self._font(13))
        self.channel_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.scan_limit_var = ctk.StringVar(value="50")
        ctk.CTkLabel(ch_frame, text="จำนวน:", font=self._font(12)).pack(side="right", padx=(6, 2))
        self.scan_limit_entry = ctk.CTkEntry(ch_frame, textvariable=self.scan_limit_var,
                                              width=50, font=self._font(12))
        self.scan_limit_entry.pack(side="right", padx=(0, 4))

        self.scan_btn = ctk.CTkButton(ch_frame, text="สแกน", width=100, font=self._font(13),
                                       command=self._on_scan_channel)
        self.scan_btn.pack(side="right")

        ctrl_frame = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=8, pady=(0, 2))

        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(ctrl_frame, text="เลือกทั้งหมด",
                                              variable=self.select_all_var, font=self._font(13),
                                              command=self._toggle_select_all)
        self.select_all_cb.pack(side="left")

        self.batch_dl_btn = ctk.CTkButton(ctrl_frame, text="ดาวน์โหลดที่เลือก", width=160,
                                           font=self._font(13), command=self._on_batch_download)
        self.batch_dl_btn.pack(side="right")

        self.channel_scroll = ctk.CTkScrollableFrame(tab, height=150)
        self.channel_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self._channel_vars = []
        self._channel_videos = []

        self.batch_progress = ctk.CTkLabel(tab, text="", font=self._font(13))
        self.batch_progress.pack(anchor="w", padx=8, pady=(0, 4))

    def _on_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.dl_progress.configure(text="กรุณาใส่ลิงก์ YouTube")
            return

        self.download_btn.configure(state="disabled")
        self.dl_result_frame.pack_forget()

        # Warn if URL contains a playlist param (prepend to progress text)
        if 'list=' in url:
            self.dl_progress.configure(
                text="[มี playlist — ใช้สแกนด้านล่าง] กำลังดาวน์โหลดเฉพาะคลิปนี้...")
        else:
            self.dl_progress.configure(text="กำลังดาวน์โหลด... อาจใช้เวลาสักครู่")
        self.status_var.set("กำลังดาวน์โหลดเพลง...")

        def task():
            try:
                temp_folder = os.path.join(DOWNLOADS_FOLDER, f"temp_{int(datetime.now().timestamp())}")
                os.makedirs(temp_folder, exist_ok=True)
                output_template = os.path.join(temp_folder, "%(title)s.%(ext)s")

                # Get channel/artist name first
                artist_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--print", "channel",
                    "--no-playlist",
                    url,
                ]
                artist_result = subprocess.run(artist_cmd, capture_output=True, text=True, timeout=30)
                artist_name = artist_result.stdout.strip() if artist_result.returncode == 0 else ""

                cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "-f", "bestaudio",
                    "-x",
                    "--audio-format", "mp3",
                    "--audio-quality", "192K",
                    "-o", output_template,
                    "--no-playlist",
                    url,
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                if result.returncode != 0:
                    self.after(0, lambda: self._dl_done(None, f"ดาวน์โหลดไม่สำเร็จ:\n{result.stderr[:300]}"))
                    return

                mp3_files = [f for f in os.listdir(temp_folder) if f.endswith(".mp3")]
                if not mp3_files:
                    self.after(0, lambda: self._dl_done(None, "ไม่พบไฟล์ MP3 หลังดาวน์โหลด"))
                    return

                mp3_file = mp3_files[0]
                song_title = mp3_file.replace(".mp3", "")
                safe_name = self._sanitize_filename(song_title) + ".mp3"
                final_path = os.path.join(DOWNLOADS_FOLDER, safe_name)
                os.replace(os.path.join(temp_folder, mp3_file), final_path)
                _cleanup_temp_folders()

                file_size = os.path.getsize(final_path) / (1024 * 1024)

                track_info = {
                    "title": song_title,
                    "youtube_url": url,
                    "file_path": final_path,
                    "filename": safe_name,
                    "file_size_mb": round(file_size, 2),
                    "artist": artist_name or "ไม่ทราบ",
                    "duration": "0:00",
                }
                add_track(track_info)

                self.after(0, lambda: self._dl_done(track_info, None))

            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._dl_done(None, "ดาวน์โหลดหมดเวลา (5 นาที)"))
            except Exception as e:
                self.after(0, lambda: self._dl_done(None, str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _dl_done(self, track: Optional[dict], error: Optional[str]):
        self.download_btn.configure(state="normal")
        if error:
            self.dl_progress.configure(text=f"ผิดพลาด: {error}")
            self.status_var.set("ดาวน์โหลดไม่สำเร็จ")
            return

        self.dl_progress.configure(text="ดาวน์โหลดเสร็จแล้ว!")
        self.dl_result_label.configure(
            text=f"ชื่อเพลง:  {track['title']}\n"
                 f"ขนาด:     {track['file_size_mb']} MB\n"
                 f"สถานะ:    เสร็จสมบูรณ์"
        )
        self.dl_result_frame.pack(fill="x", padx=8, pady=4)
        self.status_var.set(f"ดาวน์โหลดแล้ว: {track['title']}")
        self._refresh_library()
        self._refresh_track_dropdown()

    # -----------------------------------------------------------------------
    # Channel Scanner
    # -----------------------------------------------------------------------

    @staticmethod
    def _sanitize_filename(name: str, max_length: int = 80) -> str:
        """Remove Windows-invalid chars and truncate filename."""
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        name = re.sub(r'\s+', '_', name)
        if len(name) > max_length:
            name = name[:max_length]
        return name.strip('_') or "untitled"

    @staticmethod
    def _classify_url(url: str):
        """Classify a YouTube URL into (type, clean_url).

        Supports: youtube.com, music.youtube.com, youtu.be, /shorts/, /live/

        Returns one of:
        - ("video", url)     — single video, short, or live stream
        - ("playlist", url)  — playlist or watch?v=...&list=...
        - ("releases", url)  — channel releases tab
        - ("channel", url)   — channel (appends /videos if needed)
        """
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')

        # Playlist page: /playlist?list=...
        if path == '/playlist' and 'list' in qs:
            return ("playlist", url)

        # Watch page
        if '/watch' in path and 'v' in qs:
            if 'list' in qs:
                return ("playlist", url)
            return ("video", url)

        # Short URL: youtu.be/<id>
        if parsed.hostname in ('youtu.be', 'www.youtu.be'):
            if 'list' in qs:
                return ("playlist", url)
            return ("video", url)

        # Shorts: /shorts/<id>
        if re.search(r'/shorts/[A-Za-z0-9_-]+$', path):
            return ("video", url)

        # Live: /live/<id>
        if re.search(r'/live/[A-Za-z0-9_-]+$', path):
            return ("video", url)

        # Channel with /releases tab
        if re.search(r'/@[^/]+/releases$', path):
            return ("releases", url)

        # Channel already has /videos
        if re.search(r'/@[^/]+/videos$', path):
            return ("channel", url)
        if re.search(r'/(c/[^/]+|channel/[^/]+)/videos$', path):
            return ("channel", url)

        # Bare channel — append /videos
        if re.search(r'/@[^/]+$', path) or re.search(r'/(c|channel)/[^/]+$', path):
            return ("channel", url.rstrip('/') + '/videos')

        # Fallback: treat as channel, append /videos
        return ("channel", url.rstrip('/') + '/videos')

    def _on_scan_channel(self):
        channel_url = self.channel_url_entry.get().strip()
        if not channel_url:
            self.batch_progress.configure(text="กรุณาใส่ลิงก์ช่อง / playlist / releases")
            return

        # Classify the URL
        url_type, channel_url = self._classify_url(channel_url)

        # Single video — redirect user to the download field
        if url_type == "video":
            self.batch_progress.configure(
                text="ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน")
            return

        type_labels = {
            "playlist": "Playlist",
            "releases": "Releases",
            "channel": "Channel",
        }
        type_label = type_labels.get(url_type, url_type)

        # Parse scan limit
        try:
            limit = max(1, int(self.scan_limit_var.get()))
        except ValueError:
            limit = 50

        self.scan_btn.configure(state="disabled")
        self.batch_progress.configure(text=f"กำลังสแกน {type_label} (สูงสุด {limit} คลิป)...")
        self.status_var.set(f"กำลังสแกน {type_label}...")

        def task():
            try:
                cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--flat-playlist",
                    "--playlist-end", str(limit),
                    "--print", "%(id)s|||%(title)s",
                    channel_url,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                if result.returncode != 0:
                    self.after(0, lambda: self._scan_done([], f"สแกนไม่สำเร็จ:\n{result.stderr[:300]}"))
                    return

                videos = []
                for line in result.stdout.strip().split('\n'):
                    if '|||' in line:
                        vid_id, title = line.split('|||', 1)
                        videos.append({"id": vid_id.strip(), "title": title.strip()})

                self.after(0, lambda v=videos: self._scan_done(v, None))

            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._scan_done([], "สแกนหมดเวลา (2 นาที)"))
            except Exception as e:
                self.after(0, lambda err=str(e): self._scan_done([], err))

        threading.Thread(target=task, daemon=True).start()

    def _scan_done(self, videos: list, error: Optional[str]):
        self.scan_btn.configure(state="normal")

        for w in self.channel_scroll.winfo_children():
            w.destroy()
        self._channel_vars = []
        self._channel_videos = []
        self.select_all_var.set(False)

        if error:
            self.batch_progress.configure(text=f"ผิดพลาด: {error}")
            self.status_var.set("สแกนไม่สำเร็จ")
            return

        if not videos:
            self.batch_progress.configure(text="ไม่พบวิดีโอในช่อง")
            return

        self._channel_videos = videos
        self.batch_progress.configure(text=f"พบ {len(videos)} วิดีโอ")
        self.status_var.set(f"สแกนเสร็จ — พบ {len(videos)} วิดีโอ")

        for i, vid in enumerate(videos):
            var = ctk.BooleanVar(value=False)
            self._channel_vars.append(var)
            ctk.CTkCheckBox(
                self.channel_scroll,
                text=f"{i + 1}. {vid['title']}",
                variable=var,
                font=self._font(12),
            ).pack(anchor="w", padx=4, pady=1)

    def _toggle_select_all(self):
        state = self.select_all_var.get()
        for var in self._channel_vars:
            var.set(state)

    def _on_batch_download(self):
        selected = [
            self._channel_videos[i]
            for i, var in enumerate(self._channel_vars)
            if var.get()
        ]

        if not selected:
            self.batch_progress.configure(text="กรุณาเลือกอย่างน้อย 1 วิดีโอ")
            return

        self.scan_btn.configure(state="disabled")
        self.batch_dl_btn.configure(state="disabled")
        total = len(selected)
        self.batch_progress.configure(text=f"เริ่มดาวน์โหลด 0/{total}...")
        self.status_var.set(f"เริ่มดาวน์โหลด batch {total} เพลง...")

        def task():
            success = 0
            for idx, vid in enumerate(selected):
                video_url = f"https://www.youtube.com/watch?v={vid['id']}"
                short_title = vid['title'][:40]
                self.after(0, lambda i=idx + 1, t=short_title, n=total:
                    self.batch_progress.configure(text=f"ดาวน์โหลด {i}/{n}... {t}"))

                try:
                    temp_folder = os.path.join(DOWNLOADS_FOLDER, f"temp_{int(datetime.now().timestamp())}")
                    os.makedirs(temp_folder, exist_ok=True)

                    safe_title = self._sanitize_filename(vid['title'])
                    output_template = os.path.join(temp_folder, f"{safe_title}.%(ext)s")

                    artist_cmd = [
                        sys.executable, "-m", "yt_dlp",
                        "--print", "channel",
                        "--no-playlist",
                        video_url,
                    ]
                    artist_result = subprocess.run(artist_cmd, capture_output=True, text=True, timeout=30)
                    artist_name = artist_result.stdout.strip() if artist_result.returncode == 0 else ""

                    cmd = [
                        sys.executable, "-m", "yt_dlp",
                        "-f", "bestaudio",
                        "-x",
                        "--audio-format", "mp3",
                        "--audio-quality", "192K",
                        "-o", output_template,
                        "--no-playlist",
                        video_url,
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                    if result.returncode != 0:
                        logger.warning(f"Batch skip: {vid['title']} — {result.stderr[:200]}")
                        continue

                    mp3_files = [f for f in os.listdir(temp_folder) if f.endswith(".mp3")]
                    if not mp3_files:
                        logger.warning(f"Batch skip: {vid['title']} — ไม่พบไฟล์ MP3")
                        continue

                    mp3_file = mp3_files[0]
                    song_title = mp3_file.replace(".mp3", "")
                    final_path = os.path.join(DOWNLOADS_FOLDER, mp3_file)
                    os.replace(os.path.join(temp_folder, mp3_file), final_path)
                    _cleanup_temp_folders()

                    file_size = os.path.getsize(final_path) / (1024 * 1024)
                    add_track({
                        "title": song_title,
                        "youtube_url": video_url,
                        "file_path": final_path,
                        "filename": mp3_file,
                        "file_size_mb": round(file_size, 2),
                        "artist": artist_name or "ไม่ทราบ",
                        "duration": "0:00",
                    })
                    success += 1

                except Exception as e:
                    logger.warning(f"Batch skip: {vid['title']} — {e}")

                # Rate limit between downloads
                if idx < len(selected) - 1:
                    self.after(0, lambda i=idx + 1, n=total:
                        self.batch_progress.configure(
                            text=f"ดาวน์โหลด {i}/{n} เสร็จ (รอ 10 วิ. ก่อนเพลงถัดไป)"))
                    time.sleep(10)

            self.after(0, lambda s=success, t=total: self._batch_done(s, t))

        threading.Thread(target=task, daemon=True).start()

    def _batch_done(self, success: int, total: int):
        self.scan_btn.configure(state="normal")
        self.batch_dl_btn.configure(state="normal")
        self.batch_progress.configure(text=f"เสร็จ! ดาวน์โหลดสำเร็จ {success}/{total} เพลง")
        self.status_var.set(f"Batch เสร็จ — {success}/{total} เพลง")
        self._refresh_library()
        self._refresh_track_dropdown()

    # -----------------------------------------------------------------------
    # Library Tab
    # -----------------------------------------------------------------------

    def _build_library_tab(self):
        tab = self.tab_library

        top_bar = ctk.CTkFrame(tab, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 4))

        self.lib_count_label = ctk.CTkLabel(top_bar, text="เพลง: 0", font=self._font(13))
        self.lib_count_label.pack(side="left")

        refresh_btn = ctk.CTkButton(top_bar, text="รีเฟรช", width=80, font=self._font(13), command=self._refresh_library)
        refresh_btn.pack(side="right")

        open_folder_btn = ctk.CTkButton(
            top_bar, text="เปิดโฟลเดอร์", width=100, font=self._font(13),
            fg_color="#7f8c8d", hover_color="#95a5a6",
            command=lambda: os.startfile(os.path.abspath(DOWNLOADS_FOLDER)),
        )
        open_folder_btn.pack(side="right", padx=(0, 4))

        self.lib_scroll = ctk.CTkScrollableFrame(tab)
        self.lib_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._refresh_library()

    def _refresh_library(self):
        for widget in self.lib_scroll.winfo_children():
            widget.destroy()

        tracks = sync_tracks_with_folder()
        self.lib_count_label.configure(text=f"เพลง: {len(tracks)} เพลง")

        if not tracks:
            ctk.CTkLabel(self.lib_scroll, text="ยังไม่มีเพลง ลองดาวน์โหลดเพลงก่อน!",
                         font=self._font(13)).pack(pady=20)
            return

        for track in tracks:
            row = ctk.CTkFrame(self.lib_scroll)
            row.pack(fill="x", pady=2)

            text_frame = ctk.CTkFrame(row, fg_color="transparent")
            text_frame.pack(side="left", fill="x", expand=True, padx=6, pady=4)

            title = track.get('title', '?')
            if len(title) > 60:
                title = title[:57] + "..."
            ctk.CTkLabel(text_frame, text=title, anchor="w",
                         font=self._font(13, "bold")).pack(anchor="w")

            sub = (
                f"{track.get('artist', 'ไม่ทราบ')}  |  "
                f"{track.get('file_size_mb', '?')} MB  |  "
                f"{track.get('created_at', '')[:10]}"
            )
            ctk.CTkLabel(text_frame, text=sub, anchor="w",
                         font=self._font(11), text_color="gray").pack(anchor="w")

            track_id = track.get("id")
            del_btn = ctk.CTkButton(
                row, text="ลบ", width=60, fg_color="#c0392b", hover_color="#e74c3c",
                font=self._font(13),
                command=lambda tid=track_id: self._delete_track(tid),
            )
            del_btn.pack(side="right", padx=4, pady=4)

            rename_btn = ctk.CTkButton(
                row, text="แก้ชื่อ", width=70, fg_color="#2980b9", hover_color="#3498db",
                font=self._font(13),
                command=lambda tid=track_id: self._rename_track(tid),
            )
            rename_btn.pack(side="right", padx=(4, 0), pady=4)

    def _delete_track(self, track_id):
        tracks = load_tracks()
        track = next((t for t in tracks if t.get("id") == track_id), None)
        if track:
            # Delete the MP3 file from disk too
            try:
                fp = track.get("file_path", "")
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError:
                pass
        tracks = [t for t in tracks if t.get("id") != track_id]
        save_tracks(tracks)
        self._refresh_library()
        self._refresh_track_dropdown()
        self.status_var.set(f"ลบเพลง #{track_id} แล้ว")

    def _rename_track(self, track_id):
        tracks = load_tracks()
        track = next((t for t in tracks if t.get("id") == track_id), None)
        if not track:
            return

        old_title = track.get("title", "")
        dialog = ctk.CTkInputDialog(
            text=f"ชื่อปัจจุบัน: {old_title}\n\nใส่ชื่อใหม่:",
            title="แก้ชื่อเพลง",
        )
        new_title = dialog.get_input()

        if not new_title or not new_title.strip() or new_title.strip() == old_title:
            return

        new_title = new_title.strip()
        safe_name = self._sanitize_filename(new_title) + ".mp3"
        old_path = track["file_path"]
        new_path = os.path.join(DOWNLOADS_FOLDER, safe_name)

        if os.path.normpath(old_path) != os.path.normpath(new_path) and os.path.exists(new_path):
            self.status_var.set(f"ไฟล์ชื่อ {safe_name} มีอยู่แล้ว!")
            return

        try:
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
        except OSError as e:
            self.status_var.set(f"เปลี่ยนชื่อไม่สำเร็จ: {e}")
            return

        track["title"] = new_title
        track["filename"] = safe_name
        track["file_path"] = new_path
        save_tracks(tracks)

        self._refresh_library()
        self._refresh_track_dropdown()
        self.status_var.set(f"เปลี่ยนชื่อเป็น: {new_title}")

    # -----------------------------------------------------------------------
    # Create Short Tab
    # -----------------------------------------------------------------------

    def _build_create_tab(self):
        tab = self.tab_create

        # Track selector
        sel_frame = ctk.CTkFrame(tab, fg_color="transparent")
        sel_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(sel_frame, text="เลือกเพลง:", font=self._font(13)).pack(side="left", padx=(0, 6))

        self.track_var = ctk.StringVar(value="")
        self.track_dropdown = ctk.CTkComboBox(sel_frame, variable=self.track_var, values=[], width=340, state="readonly", font=self._font(13), dropdown_font=self._font(13))
        self.track_dropdown.pack(side="left", fill="x", expand=True)

        # Options row
        opts_frame = ctk.CTkFrame(tab, fg_color="transparent")
        opts_frame.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(opts_frame, text="ความยาวฮุก (วินาที):", font=self._font(13)).pack(side="left", padx=(0, 4))
        self.hook_length_var = ctk.IntVar(value=30)
        self.hook_slider = ctk.CTkSlider(opts_frame, from_=10, to=60, number_of_steps=50, variable=self.hook_length_var, width=160)
        self.hook_slider.pack(side="left", padx=(0, 4))
        self.hook_length_label = ctk.CTkLabel(opts_frame, text="30 วิ.", width=46, font=self._font(13))
        self.hook_length_label.pack(side="left", padx=(0, 12))
        self.hook_length_var.trace_add("write", lambda *_: self.hook_length_label.configure(text=f"{self.hook_length_var.get()} วิ."))

        ctk.CTkLabel(opts_frame, text="สไตล์ MV:", font=self._font(13)).pack(side="left", padx=(0, 4))
        self.style_var = ctk.StringVar(value="Thai")
        self.style_dropdown = ctk.CTkComboBox(opts_frame, variable=self.style_var,
                                               values=["Thai", "Chinese", "Japanese", "Korean",
                                                        "Laos", "Vietnamese", "Indie", "Western",
                                                        "Latin", "African"],
                                               width=130, state="readonly", font=self._font(13))
        self.style_dropdown.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(opts_frame, text="แพลตฟอร์ม:", font=self._font(13)).pack(side="left", padx=(0, 4))
        self.platform_var = ctk.StringVar(value="TikTok")
        self.platform_dropdown = ctk.CTkComboBox(opts_frame, variable=self.platform_var,
                                                  values=["TikTok", "Reels", "YouTube Shorts"],
                                                  width=140, state="readonly", font=self._font(13))
        self.platform_dropdown.pack(side="left")

        # Font style row
        font_frame = ctk.CTkFrame(tab, fg_color="transparent")
        font_frame.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(font_frame, text="สไตล์ตัวอักษร:", font=self._font(13)).pack(side="left", padx=(0, 4))
        self.font_style_var = ctk.StringVar(value="ลายมือพู่กัน")
        self.font_style_dropdown = ctk.CTkComboBox(
            font_frame, variable=self.font_style_var,
            values=[
                "ลายมือพู่กัน",
                "โปสเตอร์หนังไทย",
                "โค้งมน ชิลคาเฟ่",
                "ชอล์กอินดี้",
                "ชอล์กกระดานดำ",
                "ลายมืออินดี้",
                "พู่กันสะบัดแรง",
                "พู่กันโรแมนติก",
                "พู่กันธรรมชาติ",
                "คลาสสิก มีเชิง",
                "โค้งมน นุ่มนวล",
                "พู่กันเส้นยาว",
                "Cursive โรแมนติก",
                "Bold Grunge",
                "Modern Brush",
            ],
            width=200, state="readonly", font=self._font(13), dropdown_font=self._font(13),
        )
        self.font_style_dropdown.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(font_frame, text="มุม:", font=self._font(13)).pack(side="left", padx=(0, 4))
        self.font_angle_var = ctk.StringVar(value="เฉียงขึ้น")
        self.font_angle_dropdown = ctk.CTkComboBox(font_frame, variable=self.font_angle_var,
                                                     values=["ปกติ", "เฉียงขึ้น"],
                                                     width=100, state="readonly", font=self._font(13), dropdown_font=self._font(13))
        self.font_angle_dropdown.pack(side="left")

        # Prompt editor
        prompt_header = ctk.CTkFrame(tab, fg_color="transparent")
        prompt_header.pack(fill="x", padx=8, pady=(8, 2))

        ctk.CTkLabel(prompt_header, text="Image Prompt:", font=self._font(13, "bold")).pack(side="left")
        self.preview_prompt_btn = ctk.CTkButton(prompt_header, text="สร้าง Prompt", width=120,
                                                 font=self._font(12), command=self._on_preview_prompt)
        self.preview_prompt_btn.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(prompt_header, text="(ว่าง = สร้างอัตโนมัติ)", font=self._font(11),
                     text_color="gray").pack(side="left", padx=(8, 0))

        self.prompt_textbox = ctk.CTkTextbox(tab, height=80, font=self._font(12), wrap="word")
        self.prompt_textbox.pack(fill="x", padx=8, pady=(0, 4))

        # Image generator mode toggle
        gen_mode_frame = ctk.CTkFrame(tab, fg_color="transparent")
        gen_mode_frame.pack(fill="x", padx=8, pady=(4, 2))

        self.gemini_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(gen_mode_frame, text="ใช้ Gemini เท่านั้น (ข้าม Kie.ai)",
                        variable=self.gemini_only_var, font=self._font(12)).pack(side="left")
        ctk.CTkLabel(gen_mode_frame, text="— เลือกเมื่อ Kie.ai เครดิตหมด",
                     font=self._font(11), text_color="gray").pack(side="left", padx=(6, 0))

        # Generate button
        self.generate_btn = ctk.CTkButton(tab, text="สร้างวิดีโอสั้น", width=180, font=self._font(14, "bold"), command=self._on_generate)
        self.generate_btn.pack(pady=(4, 4))

        # Progress
        self.gen_progress = ctk.CTkLabel(tab, text="", font=self._font(13), wraplength=700, justify="left")
        self.gen_progress.pack(anchor="w", padx=8, pady=(2, 2))

        # Image preview
        self.preview_label = ctk.CTkLabel(tab, text="")
        self.preview_label.pack(pady=(4, 4))
        self.preview_label.pack_forget()

        # Result frame
        self.gen_result_frame = ctk.CTkFrame(tab)
        self.gen_result_frame.pack(fill="x", padx=8, pady=4)
        self.gen_result_label = ctk.CTkLabel(self.gen_result_frame, text="", justify="left", anchor="w", font=self._font(13))
        self.gen_result_label.pack(fill="x", padx=8, pady=6)

        # Buttons row
        self._result_buttons = ctk.CTkFrame(self.gen_result_frame, fg_color="transparent")
        self._result_buttons.pack(fill="x", padx=8, pady=(0, 6))

        self.open_video_btn = ctk.CTkButton(self._result_buttons, text="เปิดวิดีโอ", width=140,
                                             font=self._font(13), command=self._open_video)
        self.open_video_btn.pack(side="left", padx=(0, 8))

        self.open_folder_btn = ctk.CTkButton(self._result_buttons, text="เปิดโฟลเดอร์", width=140,
                                              font=self._font(13), command=self._open_outputs)
        self.open_folder_btn.pack(side="left")

        self.gen_result_frame.pack_forget()

        self._last_video_path = None
        self._refresh_track_dropdown()

    def _platform_key(self) -> str:
        mapping = {"TikTok": "tiktok", "Reels": "reels", "YouTube Shorts": "youtube-short"}
        return mapping.get(self.platform_var.get(), "tiktok")

    def _refresh_track_dropdown(self):
        tracks = load_tracks()
        values = [f"{t['id']}: {t['title']}" for t in tracks]
        self.track_dropdown.configure(values=values if values else ["(ยังไม่มีเพลง)"])
        if values:
            self.track_var.set(values[0])
        else:
            self.track_var.set("(ยังไม่มีเพลง)")

    def _selected_track(self) -> Optional[dict]:
        val = self.track_var.get()
        if not val or val == "(ยังไม่มีเพลง)":
            return None
        try:
            track_id = int(val.split(":")[0])
        except ValueError:
            return None
        tracks = load_tracks()
        return next((t for t in tracks if t.get("id") == track_id), None)

    def _show_image_preview(self, image_path: str):
        """Show album art preview in the GUI."""
        try:
            pil_img = PILImage.open(image_path)
            # Scale to fit — max 200px height
            ratio = 200 / pil_img.height
            new_w = int(pil_img.width * ratio)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, 200))
            self.preview_label.configure(image=ctk_img, text="")
            self.preview_label._ctk_image = ctk_img  # prevent GC
            self.preview_label.pack(pady=(4, 4))
        except Exception as e:
            logger.warning(f"Could not show preview: {e}")

    def _on_preview_prompt(self):
        """Build image prompt from current settings and show in textbox."""
        track = self._selected_track()
        if not track:
            self.gen_progress.configure(text="กรุณาเลือกเพลงก่อน")
            return

        self.preview_prompt_btn.configure(state="disabled")
        self.gen_progress.configure(text="กำลังสร้าง Prompt...")

        video_style = self.style_var.get()
        font_style = self.font_style_var.get()
        font_angle = self.font_angle_var.get()

        def task():
            try:
                filename = Path(track["file_path"]).stem
                metadata = extract_metadata_from_title(filename)
                song_title = metadata["song"]
                artist = track.get("artist", "") or metadata["artist"]
                if artist == "ไม่ทราบ":
                    artist = metadata["artist"]

                detector = MoodDetector()
                mood_info = detector.detect_from_artist_title(artist, song_title)

                gen = KieAIGenerator()
                prompt = gen._build_prompt(
                    song_title, mood_info["mood"], mood_info["intensity"],
                    video_style, font_style, font_angle, artist,
                )
                self.after(0, lambda p=prompt: self._show_prompt(p))
            except Exception as e:
                self.after(0, lambda err=str(e): self.gen_progress.configure(text=f"ผิดพลาด: {err}"))
                self.after(0, lambda: self.preview_prompt_btn.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _show_prompt(self, prompt: str):
        self.preview_prompt_btn.configure(state="normal")
        self.prompt_textbox.delete("1.0", "end")
        self.prompt_textbox.insert("1.0", prompt)
        self.gen_progress.configure(text="Prompt พร้อมแล้ว — แก้ไขได้ก่อนกดสร้าง")

    def _on_generate(self):
        track = self._selected_track()
        if not track:
            self.gen_progress.configure(text="กรุณาเลือกเพลงก่อน")
            return

        audio_path = track["file_path"]
        if not os.path.exists(audio_path):
            self.gen_progress.configure(text=f"ไม่พบไฟล์เพลง: {audio_path}")
            return

        hook_length = self.hook_length_var.get()
        platform = self._platform_key()
        video_style = self.style_var.get()
        font_style = self.font_style_var.get()
        font_angle = self.font_angle_var.get()
        custom_prompt = self.prompt_textbox.get("1.0", "end").strip()

        self.generate_btn.configure(state="disabled")
        self.gen_result_frame.pack_forget()
        self.preview_label.pack_forget()
        self._gen_step("เริ่มต้น...")

        def task():
            try:
                # Step 1: Metadata — use artist from track data (YouTube channel)
                self._gen_step("ขั้น 1/6  ดึงข้อมูลเพลง...")
                filename = Path(audio_path).stem
                metadata = extract_metadata_from_title(filename)
                song_title = metadata["song"]
                # Prefer artist from track (YouTube channel) over filename parse
                artist = track.get("artist", "") or metadata["artist"]
                if artist == "ไม่ทราบ":
                    artist = metadata["artist"]

                # Step 2: Mood detection
                self._gen_step(f"ขั้น 2/6  ตรวจอารมณ์เพลง '{song_title}'...")
                detector = MoodDetector()
                mood_info = detector.detect_from_artist_title(artist, song_title)
                mood = mood_info["mood"]
                intensity = mood_info["intensity"]

                # Step 3: Hook extraction (use ASCII temp path to avoid Thai encoding issues)
                # Check cache — include length in filename so different lengths get separate files
                hook_filename = f"{song_title.replace(' ', '_')}_hook_{hook_length}s.wav"
                hook_path = os.path.join(OUTPUTS_FOLDER, hook_filename)

                if os.path.exists(hook_path):
                    self._gen_step("ขั้น 3/6  ใช้ท่อนฮุกจาก cache...")
                    logger.info(f"Hook cache hit: {hook_path}")
                else:
                    self._gen_step("ขั้น 3/6  ตัดท่อนฮุก (อาจใช้เวลาสักครู่)...")
                    tmp_hook = os.path.join(OUTPUTS_FOLDER, f"_tmp_hook_{int(datetime.now().timestamp())}.wav")
                    from python.main import extract_hook as _extract_hook
                    if not _extract_hook(audio_path, tmp_hook, hook_length):
                        if os.path.exists(tmp_hook):
                            os.remove(tmp_hook)
                        self.after(0, lambda: self._gen_done(None, "ตัดท่อนฮุกไม่สำเร็จ — อาจไม่พบท่อน chorus"))
                        return
                    # Rename temp to final path
                    os.replace(tmp_hook, hook_path)

                # Step 4: Album art
                art_filename = f"{song_title.replace(' ', '_')}_art.png"
                art_path = os.path.join(OUTPUTS_FOLDER, art_filename)
                image_path = None
                gemini_only = self.gemini_only_var.get()

                if not gemini_only:
                    self._gen_step("ขั้น 4/6  สร้างภาพปกด้วย AI (Kie.ai)...")
                    gen = KieAIGenerator()
                    image_path = gen.generate_album_art(
                        song_title=song_title,
                        mood=mood,
                        intensity=intensity,
                        output_path=art_path,
                        video_style=video_style,
                        font_style=font_style,
                        font_angle=font_angle,
                        artist=artist,
                        custom_prompt=custom_prompt,
                    )
                    if not image_path:
                        logger.warning("Kie.ai failed — falling back to Gemini...")

                if not image_path:
                    label = "ขั้น 4/6  สร้างภาพปกด้วย Gemini..." if gemini_only else "ขั้น 4/6  Fallback: สร้างภาพปกด้วย Gemini..."
                    self._gen_step(label)
                    gemini_gen = GeminiImageGenerator()
                    image_path = gemini_gen.generate_album_art(
                        song_title=song_title,
                        mood=mood,
                        intensity=intensity,
                        output_path=art_path,
                        video_style=video_style,
                        font_style=font_style,
                        font_angle=font_angle,
                        artist=artist,
                        custom_prompt=custom_prompt,
                    )
                if not image_path:
                    fail_src = "Gemini" if gemini_only else "Kie.ai + Gemini"
                    self.after(0, lambda: self._gen_done(None, f"สร้างภาพปกไม่สำเร็จ ({fail_src})"))
                    return

                # Show image preview
                self.after(0, lambda p=image_path: self._show_image_preview(p))

                # Step 5: Video composition
                self._gen_step("ขั้น 5/6  ตัดต่อวิดีโอ...")
                video_filename = f"{song_title.replace(' ', '_')}_short.mp4"
                video_path = os.path.join(OUTPUTS_FOLDER, video_filename)
                vid = compose_complete_short(
                    image_path=image_path,
                    hook_audio_path=hook_path,
                    output_path=video_path,
                    song_title=song_title,
                    platform=platform,
                )
                if not vid:
                    self.after(0, lambda: self._gen_done(None, "ตัดต่อวิดีโอไม่สำเร็จ"))
                    return

                # Step 6: Done — clean up temp files
                _cleanup_temp_hooks()

                result = {
                    "song_title": song_title,
                    "mood": mood,
                    "image_path": image_path,
                    "hook_path": hook_path,
                    "video_path": vid,
                }
                self.after(0, lambda: self._gen_done(result, None))

            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._gen_done(None, "ตัดท่อนฮุกหมดเวลา (5 นาที)"))
            except Exception as e:
                self.after(0, lambda: self._gen_done(None, str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _gen_step(self, text: str):
        self.after(0, lambda: self.gen_progress.configure(text=text))
        self.after(0, lambda: self.status_var.set(text))

    def _gen_done(self, result: Optional[dict], error: Optional[str]):
        self.generate_btn.configure(state="normal")
        if error:
            self.gen_progress.configure(text=f"ผิดพลาด: {error}")
            self.status_var.set("สร้างวิดีโอไม่สำเร็จ")
            return

        self._last_video_path = result['video_path']
        self.gen_progress.configure(text="เสร็จสมบูรณ์!")
        self.gen_result_label.configure(
            text=(
                f"ชื่อเพลง:   {result['song_title']}\n"
                f"อารมณ์:     {result['mood']}\n"
                f"ภาพปก:    {Path(result['image_path']).name}\n"
                f"ท่อนฮุก:   {Path(result['hook_path']).name}\n"
                f"วิดีโอ:    {Path(result['video_path']).name}"
            )
        )
        self.gen_result_frame.pack(fill="x", padx=8, pady=4)
        self.status_var.set(f"สร้างเสร็จ: {result['song_title']}")

        # Auto-upload if enabled
        if self.auto_upload_var.get():
            self._auto_upload_video(result['video_path'], result['song_title'])

    def _auto_upload_video(self, video_path: str, title: str):
        """Trigger upload for a newly created video using upload tab settings."""
        platforms = []
        if self.upload_yt_var.get():
            platforms.append("youtube")
        if self.upload_tt_var.get():
            platforms.append("tiktok")
        if self.upload_fb_var.get():
            platforms.append("facebook")

        if not platforms:
            self.gen_progress.configure(
                text="เสร็จสมบูรณ์! (อัปโหลดอัตโนมัติ: ไม่มีแพลตฟอร์มที่เลือก)")
            return

        # Filter out unconfigured platforms for auto-upload (skip silently)
        s = load_settings()
        ready = []
        for p in platforms:
            if p == "youtube" and os.path.exists("client_secrets.json"):
                ready.append(p)
            elif p == "tiktok" and TikTokBrowserUploader().is_configured():
                ready.append(p)
            elif p == "facebook" and s.get("facebook_access_token"):
                ready.append(p)
        skipped = len(platforms) - len(ready)
        platforms = ready

        if not platforms:
            self.gen_progress.configure(
                text="เสร็จสมบูรณ์! (อัปโหลดอัตโนมัติ: ไม่มีแพลตฟอร์มที่ตั้งค่าแล้ว)")
            return

        tags_raw = self.upload_tags_var.get().strip()
        tags = [t.strip().replace("#", "") for t in tags_raw.split(",") if t.strip()]
        publish_mode = self.upload_privacy_var.get()
        promo_link = self.upload_promo_link_var.get().strip()
        auto_desc = promo_link if promo_link else ""
        fname = os.path.basename(video_path)

        self.gen_progress.configure(text="เสร็จสมบูรณ์! กำลังอัปโหลดอัตโนมัติ...")
        self.status_var.set("อัปโหลดอัตโนมัติ...")

        def task():
            results = self._upload_single(video_path, title, auto_desc, tags, publish_mode, platforms,
                                          step_prefix="[auto] ")
            add_upload_record(fname, results)
            success = sum(1 for r in results if r.status == UploadStatus.SUCCESS)
            total = len(results)

            def done():
                self._refresh_upload_history()
                self._refresh_upload_videos()
                self.gen_progress.configure(
                    text=f"เสร็จสมบูรณ์! อัปโหลดอัตโนมัติ {success}/{total}")
                self.status_var.set(f"อัปโหลดอัตโนมัติเสร็จ — {success}/{total}")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _open_video(self):
        if self._last_video_path and os.path.exists(self._last_video_path):
            path = os.path.abspath(self._last_video_path)
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

    def _open_outputs(self):
        folder = os.path.abspath(OUTPUTS_FOLDER)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    # -----------------------------------------------------------------------
    # Upload Tab
    # -----------------------------------------------------------------------

    def _build_upload_tab(self):
        tab = self.tab_upload

        # Video selector — multi-select with checkboxes
        sel_header = ctk.CTkFrame(tab, fg_color="transparent")
        sel_header.pack(fill="x", padx=8, pady=(8, 2))

        ctk.CTkLabel(sel_header, text="เลือกวิดีโอ:", font=self._font(13)).pack(side="left", padx=(0, 6))

        self._upload_select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(sel_header, text="เลือกทั้งหมด", variable=self._upload_select_all_var,
                        font=self._font(11), command=self._toggle_select_all_videos).pack(side="left", padx=(8, 0))

        ctk.CTkButton(sel_header, text="รีเฟรช", width=70, font=self._font(12),
                       command=self._refresh_upload_videos).pack(side="right")

        ctk.CTkButton(
            sel_header, text="เปิดโฟลเดอร์", width=100, font=self._font(12),
            fg_color="#7f8c8d", hover_color="#95a5a6",
            command=lambda: os.startfile(os.path.abspath(OUTPUTS_FOLDER)),
        ).pack(side="right", padx=(0, 4))

        self._upload_video_list_frame = ctk.CTkScrollableFrame(tab, height=80)
        self._upload_video_list_frame.pack(fill="x", padx=8, pady=(0, 4))
        self._upload_video_checks: list[tuple[ctk.BooleanVar, str]] = []  # (var, filename)

        # Selected video info
        self.upload_info_label = ctk.CTkLabel(tab, text="", font=self._font(11),
                                               text_color="gray", anchor="w")
        self.upload_info_label.pack(fill="x", padx=8, pady=(0, 4))

        # Keep upload_video_var for compatibility (stores last/primary selection)
        self.upload_video_var = ctk.StringVar(value="")

        # Title
        title_frame = ctk.CTkFrame(tab, fg_color="transparent")
        title_frame.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(title_frame, text="ชื่อ:", font=self._font(13), width=80, anchor="w").pack(side="left")
        self.upload_title_var = ctk.StringVar(value="")
        ctk.CTkEntry(title_frame, textvariable=self.upload_title_var, font=self._font(13)).pack(
            side="left", fill="x", expand=True)

        # Description
        desc_frame = ctk.CTkFrame(tab, fg_color="transparent")
        desc_frame.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(desc_frame, text="คำอธิบาย:", font=self._font(13), width=80, anchor="w").pack(side="left")
        self.upload_desc_textbox = ctk.CTkTextbox(desc_frame, height=50, font=self._font(12), wrap="word")
        self.upload_desc_textbox.pack(side="left", fill="x", expand=True)

        # Hashtags
        tags_frame = ctk.CTkFrame(tab, fg_color="transparent")
        tags_frame.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(tags_frame, text="แฮชแท็ก:", font=self._font(13), width=80, anchor="w").pack(side="left")
        self.upload_tags_var = ctk.StringVar(value="Shorts, เพลง, เพลงไทย, HookToShort")
        ctk.CTkEntry(tags_frame, textvariable=self.upload_tags_var, font=self._font(13),
                     placeholder_text="คั่นด้วย comma").pack(side="left", fill="x", expand=True)

        # Promo Link
        link_frame = ctk.CTkFrame(tab, fg_color="transparent")
        link_frame.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(link_frame, text="Promo Link:", font=self._font(13), width=80, anchor="w").pack(side="left")
        self.upload_promo_link_var = ctk.StringVar(value="")
        ctk.CTkEntry(link_frame, textvariable=self.upload_promo_link_var, font=self._font(13),
                     placeholder_text="เช่น Spotify, YouTube, เว็บไซต์").pack(side="left", fill="x", expand=True)

        # Publish mode (privacy + scheduling)
        priv_frame = ctk.CTkFrame(tab, fg_color="transparent")
        priv_frame.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(priv_frame, text="เผยแพร่:", font=self._font(13), width=120, anchor="w").pack(side="left")
        self.upload_privacy_var = ctk.StringVar(value="โพสทันที")
        ctk.CTkComboBox(priv_frame, variable=self.upload_privacy_var,
                        values=list(PUBLISH_MODES.keys()),
                        width=180, state="readonly", font=self._font(13),
                        command=self._on_publish_mode_changed).pack(side="left")
        self.schedule_info_label = ctk.CTkLabel(priv_frame, text="", font=self._font(11), text_color="#3498db")
        self.schedule_info_label.pack(side="left", padx=(8, 0))

        # Platform toggles
        plat_frame = ctk.CTkFrame(tab)
        plat_frame.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(plat_frame, text="แพลตฟอร์ม:", font=self._font(13, "bold")).pack(
            anchor="w", padx=8, pady=(6, 4))

        plat_inner = ctk.CTkFrame(plat_frame, fg_color="transparent")
        plat_inner.pack(fill="x", padx=8, pady=(0, 6))

        self.upload_yt_var = ctk.BooleanVar(value=True)
        self.upload_tt_var = ctk.BooleanVar(value=False)
        self.upload_fb_var = ctk.BooleanVar(value=False)

        yt_col = ctk.CTkFrame(plat_inner, fg_color="transparent")
        yt_col.pack(side="left", expand=True, fill="x")
        ctk.CTkCheckBox(yt_col, text="YouTube Shorts", variable=self.upload_yt_var,
                        font=self._font(13)).pack(anchor="w")
        yt_status_row = ctk.CTkFrame(yt_col, fg_color="transparent")
        yt_status_row.pack(anchor="w", padx=(26, 0))
        self.yt_status_label = ctk.CTkLabel(yt_status_row, text="", font=self._font(11), text_color="gray")
        self.yt_status_label.pack(side="left")
        self.yt_manual_btn = ctk.CTkButton(
            yt_status_row, text="อัปโหลดเอง", width=70, height=20, font=self._font(10),
            fg_color="transparent", text_color="#3498db", hover_color=("gray85", "gray30"),
            command=lambda: webbrowser.open("https://studio.youtube.com/"))
        self.yt_manual_btn.pack(side="left", padx=(4, 0))
        self.yt_manual_btn.pack_forget()

        tt_col = ctk.CTkFrame(plat_inner, fg_color="transparent")
        tt_col.pack(side="left", expand=True, fill="x")
        ctk.CTkCheckBox(tt_col, text="TikTok", variable=self.upload_tt_var,
                        font=self._font(13)).pack(anchor="w")
        tt_status_row = ctk.CTkFrame(tt_col, fg_color="transparent")
        tt_status_row.pack(anchor="w", padx=(26, 0))
        self.tt_status_label = ctk.CTkLabel(tt_status_row, text="", font=self._font(11), text_color="gray")
        self.tt_status_label.pack(side="left")
        self.tt_manual_btn = ctk.CTkButton(
            tt_status_row, text="อัปโหลดเอง", width=70, height=20, font=self._font(10),
            fg_color="transparent", text_color="#3498db", hover_color=("gray85", "gray30"),
            command=lambda: webbrowser.open("https://www.tiktok.com/upload"))
        self.tt_manual_btn.pack(side="left", padx=(4, 0))
        self.tt_manual_btn.pack_forget()

        fb_col = ctk.CTkFrame(plat_inner, fg_color="transparent")
        fb_col.pack(side="left", expand=True, fill="x")
        ctk.CTkCheckBox(fb_col, text="Facebook Reels", variable=self.upload_fb_var,
                        font=self._font(13)).pack(anchor="w")
        fb_status_row = ctk.CTkFrame(fb_col, fg_color="transparent")
        fb_status_row.pack(anchor="w", padx=(26, 0))
        self.fb_status_label = ctk.CTkLabel(fb_status_row, text="", font=self._font(11), text_color="gray")
        self.fb_status_label.pack(side="left")
        self.fb_manual_btn = ctk.CTkButton(
            fb_status_row, text="อัปโหลดเอง", width=70, height=20, font=self._font(10),
            fg_color="transparent", text_color="#3498db", hover_color=("gray85", "gray30"),
            command=lambda: webbrowser.open("https://business.facebook.com/latest/content_calendar"))
        self.fb_manual_btn.pack(side="left", padx=(4, 0))
        self.fb_manual_btn.pack_forget()

        # Auto-upload toggle
        auto_frame = ctk.CTkFrame(tab, fg_color="transparent")
        auto_frame.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkCheckBox(auto_frame, text="อัปโหลดอัตโนมัติหลังสร้างวิดีโอ",
                        variable=self.auto_upload_var, font=self._font(12)).pack(side="left")

        # Upload button
        self.upload_btn = ctk.CTkButton(tab, text="อัปโหลด", width=180,
                                         font=self._font(14, "bold"), command=self._on_upload)
        self.upload_btn.pack(pady=(8, 4))

        # Upload progress bar + label
        self.upload_progress_bar = ctk.CTkProgressBar(tab, width=400, height=14)
        self.upload_progress_bar.pack(fill="x", padx=8, pady=(8, 2))
        self.upload_progress_bar.set(0)
        self.upload_progress_bar.pack_forget()

        self.upload_progress = ctk.CTkLabel(tab, text="", font=self._font(13),
                                             wraplength=700, justify="left")
        self.upload_progress.pack(anchor="w", padx=8, pady=(2, 2))

        # Upload results
        self.upload_result_frame = ctk.CTkFrame(tab)
        self.upload_result_frame.pack(fill="x", padx=8, pady=4)
        self._upload_result_rows_frame = ctk.CTkFrame(self.upload_result_frame, fg_color="transparent")
        self._upload_result_rows_frame.pack(fill="x", padx=8, pady=(6, 2))
        self.upload_retry_btn = ctk.CTkButton(
            self.upload_result_frame, text="ลองอีกครั้ง", width=100, font=self._font(12),
            command=self._on_upload)
        self.upload_retry_btn.pack(padx=8, pady=(0, 6), anchor="w")
        self.upload_retry_btn.pack_forget()
        self.upload_result_frame.pack_forget()

        # Upload history
        hist_header = ctk.CTkFrame(tab, fg_color="transparent")
        hist_header.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(hist_header, text="ประวัติอัปโหลด", font=self._font(14, "bold")).pack(side="left")

        self.upload_history_box = ctk.CTkTextbox(tab, height=120, font=self._font(11),
                                                  state="disabled", wrap="word")
        self.upload_history_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Initialize
        self._refresh_upload_videos()
        self._update_platform_status()
        self._refresh_upload_history()

    def _refresh_upload_videos(self):
        videos = get_output_videos(OUTPUTS_FOLDER)
        # Clear existing checkboxes
        for widget in self._upload_video_list_frame.winfo_children():
            widget.destroy()
        self._upload_video_checks.clear()
        self._upload_select_all_var.set(False)

        if not videos:
            ctk.CTkLabel(self._upload_video_list_frame, text="(ยังไม่มีวิดีโอ)",
                         font=self._font(11), text_color="gray").pack(anchor="w")
            self.upload_info_label.configure(text="")
            self.upload_title_var.set("")
            self.upload_video_var.set("")
            return

        for vid in videos:
            var = ctk.BooleanVar(value=False)
            row = ctk.CTkFrame(self._upload_video_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            date_str = vid.get('date', '')
            ctk.CTkCheckBox(row, text=f"{vid['filename']}  ({vid['size_mb']} MB)  {date_str}",
                            variable=var, font=self._font(11),
                            command=self._on_video_check_changed).pack(side="left")
            self._upload_video_checks.append((var, vid["filename"]))

        # Select first by default
        if self._upload_video_checks:
            self._upload_video_checks[0][0].set(True)
            self._on_video_check_changed()

    def _toggle_select_all_videos(self):
        val = self._upload_select_all_var.get()
        for var, _ in self._upload_video_checks:
            var.set(val)
        self._on_video_check_changed()

    def _on_publish_mode_changed(self, _value=None):
        """Update schedule info label when publish mode changes."""
        import random as _rnd
        mode = self.upload_privacy_var.get()
        days = PUBLISH_MODES.get(mode)
        if days is None:
            self.schedule_info_label.configure(text="")
        else:
            if days == -1:  # random
                days = _rnd.randint(1, 3)
            sample = calculate_publish_time("youtube", days)
            # Show just date + time in a friendly format
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(sample)
            self.schedule_info_label.configure(
                text=f"ประมาณ {dt.strftime('%d/%m %H:%M')} (เวลาจะสุ่มตาม platform)")

    @staticmethod
    def _resolve_privacy_and_schedule(mode: str, platform: str, batch_offset: int = 0):
        """Resolve publish mode → (privacy, publish_at) per platform.

        Args:
            mode: Value from the publish mode dropdown
            platform: "youtube", "tiktok", or "facebook"
            batch_offset: Extra days to add for batch (video index)

        Returns:
            (privacy_str, publish_at_iso_or_None)
        """
        import random as _rnd
        days = PUBLISH_MODES.get(mode)
        if days is None:
            # Non-scheduled modes
            privacy_map = {"โพสทันที": "public", "ส่วนตัว": "private", "ไม่แสดง": "unlisted"}
            return privacy_map.get(mode, "public"), None

        # Scheduled mode
        if days == -1:  # random 1-3
            days = _rnd.randint(1, 3)
        days += batch_offset
        publish_at = calculate_publish_time(platform, days)
        return "public", publish_at

    def _on_video_check_changed(self):
        selected = [(var, fname) for var, fname in self._upload_video_checks if var.get()]
        count = len(selected)
        if count == 0:
            self.upload_info_label.configure(text="")
            self.upload_title_var.set("")
            self.upload_video_var.set("")
        elif count == 1:
            fname = selected[0][1]
            self.upload_video_var.set(fname)
            videos = get_output_videos(OUTPUTS_FOLDER)
            vid = next((v for v in videos if v["filename"] == fname), None)
            if vid:
                self.upload_info_label.configure(text=f"ขนาด: {vid['size_mb']} MB  |  {vid['path']}")
                self.upload_title_var.set(vid["title"])
        else:
            self.upload_video_var.set(selected[0][1])
            self.upload_info_label.configure(text=f"เลือก {count} วิดีโอ (batch upload)")
            self.upload_title_var.set("")

    def _update_platform_status(self):
        """Update configuration status labels for each platform."""
        # YouTube
        yt = YouTubeUploader()
        if yt.is_configured():
            self.yt_status_label.configure(text="พร้อม (client_secrets.json)", text_color="#2ecc71")
            self.yt_manual_btn.pack_forget()
        else:
            self.yt_status_label.configure(text="ยังไม่ตั้งค่า", text_color="#e67e22")
            self.yt_manual_btn.pack(side="left", padx=(4, 0))

        # TikTok (Browser — cookie check)
        s = load_settings()
        tt_browser = TikTokBrowserUploader()
        if tt_browser.is_configured():
            self.tt_status_label.configure(text="พร้อม (cookie)", text_color="#2ecc71")
            self.tt_manual_btn.pack_forget()
        else:
            self.tt_status_label.configure(text="ยังไม่ได้ login", text_color="#e67e22")
            self.tt_manual_btn.pack(side="left", padx=(4, 0))

        # Facebook
        fb_token = s.get("facebook_access_token", "")
        if fb_token:
            fb_id = s.get("facebook_page_id", "")
            target = f"Page: {fb_id}" if fb_id else "โปรไฟล์ส่วนตัว"
            self.fb_status_label.configure(text=f"พร้อม ({target})", text_color="#2ecc71")
            self.fb_manual_btn.pack_forget()
        else:
            self.fb_status_label.configure(text="ยังไม่ตั้งค่า", text_color="#e67e22")
            self.fb_manual_btn.pack(side="left", padx=(4, 0))

    def _refresh_upload_history(self):
        history = load_upload_history()
        self.upload_history_box.configure(state="normal")
        self.upload_history_box.delete("1.0", "end")
        if not history:
            self.upload_history_box.insert("1.0", "(ยังไม่มีประวัติอัปโหลด)")
        else:
            # Show most recent first, max 20
            for entry in reversed(history[-20:]):
                ts = entry.get("timestamp", "")[:16].replace("T", " ")
                icon = "OK" if entry.get("status") == "success" else "FAIL"
                url = entry.get("url", "")
                line = f"[{ts}] [{icon}] {entry.get('platform', '?')} — {entry.get('video', '?')}"
                if url:
                    line += f"  →  {url}"
                elif entry.get("error"):
                    line += f"  ({entry['error'][:60]})"
                self.upload_history_box.insert("end", line + "\n")
        self.upload_history_box.configure(state="disabled")

    def _get_selected_video_filenames(self) -> list[str]:
        return [fname for var, fname in self._upload_video_checks if var.get()]

    def _upload_progress_callback(self, progress: float):
        """Called from upload thread with 0.0-1.0 progress."""
        self.after(0, lambda p=progress: self.upload_progress_bar.set(p))

    def _upload_single(self, video_path: str, title: str, description: str,
                       tags: list[str], publish_mode: str, platforms: list[str],
                       step_prefix: str = "",
                       batch_offset: int = 0) -> list[UploadResult]:
        """Upload one video to selected platforms. Called from background thread.

        Note: Facebook & YouTube use title only (no description/promo link).
        TikTok gets the full description with promo link.
        """
        results = []
        total = len(platforms)
        for idx, platform in enumerate(platforms):
            step = f"{step_prefix}({idx + 1}/{total})"
            # Reset progress bar for each platform
            self.after(0, lambda: self.upload_progress_bar.set(0))

            # Resolve privacy + schedule per platform
            privacy, publish_at = self._resolve_privacy_and_schedule(
                publish_mode, platform, batch_offset)

            schedule_note = ""
            if publish_at:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(publish_at)
                schedule_note = f" (ตั้งเวลา {dt.strftime('%d/%m %H:%M')})"

            # TikTok: ignore scheduling (browser automation can't schedule)
            if platform == "tiktok" and publish_at:
                publish_at = None
                privacy = "public"
                schedule_note = " (TikTok: โพสทันที)"

            # Build request per platform
            if platform == "tiktok":
                req = UploadRequest(
                    video_path=video_path, title=title,
                    description=description, tags=tags,
                    privacy=privacy, publish_at=publish_at,
                )
            else:
                # Facebook & YouTube: title only
                req = UploadRequest(
                    video_path=video_path, title=title,
                    description="", tags=tags,
                    privacy=privacy, publish_at=publish_at,
                )

            plat_name = {"youtube": "YouTube", "tiktok": "TikTok", "facebook": "Facebook"}.get(platform, platform)
            self._upload_step(f"{step} {plat_name}: กำลังอัปโหลด...{schedule_note}")

            if platform == "youtube":
                yt = YouTubeUploader()
                result = upload_with_retry(
                    lambda: yt.upload(req, progress_callback=self._upload_progress_callback))
            elif platform == "tiktok":
                tt = TikTokBrowserUploader()
                result = upload_with_retry(
                    lambda: tt.upload(req, progress_callback=self._upload_progress_callback))
            elif platform == "facebook":
                s = load_settings()
                fb = FacebookUploader(
                    page_id=s.get("facebook_page_id", ""),
                    access_token=s.get("facebook_access_token", ""),
                )
                result = upload_with_retry(
                    lambda: fb.upload(req, progress_callback=self._upload_progress_callback))
            else:
                continue
            results.append(result)
        return results

    def _on_upload(self):
        selected_files = self._get_selected_video_filenames()
        if not selected_files:
            self.upload_progress.configure(text="กรุณาเลือกวิดีโอก่อน")
            return

        # Verify files exist
        for fname in selected_files:
            video_path = os.path.join(OUTPUTS_FOLDER, fname)
            if not os.path.exists(video_path):
                self.upload_progress.configure(text=f"ไม่พบไฟล์: {fname}")
                return

        # Check at least one platform selected
        platforms = []
        if self.upload_yt_var.get():
            platforms.append("youtube")
        if self.upload_tt_var.get():
            platforms.append("tiktok")
        if self.upload_fb_var.get():
            platforms.append("facebook")

        if not platforms:
            self.upload_progress.configure(text="กรุณาเลือกอย่างน้อย 1 แพลตฟอร์ม")
            return

        # Pre-upload credential validation
        missing = []
        s = load_settings()
        if "youtube" in platforms:
            if not os.path.exists("client_secrets.json"):
                missing.append("YouTube: ไม่พบ client_secrets.json — ไปที่ Setup Wizard หรือตั้งค่า")
        if "tiktok" in platforms:
            if not TikTokBrowserUploader().is_configured():
                missing.append("TikTok: ยังไม่ได้ login — ไปที่ตั้งค่า > Login TikTok")
        if "facebook" in platforms:
            if not s.get("facebook_access_token"):
                missing.append("Facebook: ยังไม่ได้ตั้งค่า Access Token")

        if missing:
            msg = "ตั้งค่า credentials ไม่ครบ:\n\n" + "\n".join(f"  - {m}" for m in missing)
            msg += "\n\nไปที่แท็บ 'ตั้งค่า' หรือกด Setup Wizard"
            tkmessagebox.showwarning("ยังไม่พร้อมอัปโหลด", msg)
            return

        # Shared metadata
        custom_title = self.upload_title_var.get().strip()
        description = self.upload_desc_textbox.get("1.0", "end").strip()
        promo_link = self.upload_promo_link_var.get().strip()
        if promo_link:
            description = f"{description}\n{promo_link}" if description else promo_link
        tags_raw = self.upload_tags_var.get().strip()
        tags = [t.strip().replace("#", "") for t in tags_raw.split(",") if t.strip()]
        publish_mode = self.upload_privacy_var.get()

        self.upload_btn.configure(state="disabled")
        self.upload_result_frame.pack_forget()
        self.upload_progress_bar.set(0)
        self.upload_progress_bar.pack(fill="x", padx=8, pady=(8, 2))
        self.upload_progress.configure(text="เริ่มอัปโหลด...")
        self.status_var.set("กำลังอัปโหลด...")

        is_batch = len(selected_files) > 1

        def task():
            all_results = []
            for vid_idx, fname in enumerate(selected_files):
                video_path = os.path.join(OUTPUTS_FOLDER, fname)
                # For batch: auto-generate title from filename; for single: use custom title
                if is_batch:
                    title = fname.replace("_short.mp4", "").replace("_", " ")
                    prefix = f"[{vid_idx + 1}/{len(selected_files)}] "
                    self._upload_step(f"{prefix}{fname}")
                else:
                    title = custom_title or fname.replace("_short.mp4", "").replace("_", " ")
                    prefix = ""

                # Batch: auto-space schedule (+1 day per video)
                batch_offset = vid_idx if is_batch else 0

                results = self._upload_single(video_path, title, description,
                                              tags, publish_mode, platforms, prefix,
                                              batch_offset=batch_offset)
                # Save history per video
                self.after(0, lambda f=fname, r=list(results): add_upload_record(f, r))
                all_results.extend(results)

            self.after(0, lambda r=all_results: self._upload_done_batch(r, len(selected_files)))

        threading.Thread(target=task, daemon=True).start()

    def _upload_step(self, text: str):
        self.after(0, lambda: self.upload_progress.configure(text=text))
        self.after(0, lambda: self.status_var.set(text))

    def _upload_done_batch(self, results: list[UploadResult], video_count: int):
        self.upload_btn.configure(state="normal")
        self.upload_progress_bar.set(1.0)
        self.upload_progress_bar.pack_forget()

        # Clear previous result rows
        for w in self._upload_result_rows_frame.winfo_children():
            w.destroy()

        success_count = 0
        for r in results:
            row = ctk.CTkFrame(self._upload_result_rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            if r.status == UploadStatus.SUCCESS:
                success_count += 1
                ctk.CTkLabel(row, text=f"[OK] {r.platform}", font=self._font(12),
                             text_color="#2ecc71", anchor="w").pack(side="left")
                if r.url:
                    url = r.url
                    link_btn = ctk.CTkButton(
                        row, text=url, width=0, height=22, font=self._font(11),
                        fg_color="transparent", text_color="#3498db",
                        hover_color=("gray85", "gray30"), anchor="w",
                        command=lambda u=url: webbrowser.open(u))
                    link_btn.pack(side="left", padx=(8, 0))
            else:
                ctk.CTkLabel(row, text=f"[FAIL] {r.platform}  —  {r.error or 'unknown error'}",
                             font=self._font(12), text_color="#e74c3c", anchor="w").pack(side="left")

        self._refresh_upload_history()

        total = len(results)
        summary = f"เสร็จ! สำเร็จ {success_count}/{total}"
        if video_count > 1:
            summary += f" ({video_count} วิดีโอ)"
        self.upload_progress.configure(text=summary)
        self.upload_result_frame.pack(fill="x", padx=8, pady=4)

        # Show retry button if any failed
        if success_count < total:
            self.upload_retry_btn.pack(padx=8, pady=(0, 6), anchor="w")
        else:
            self.upload_retry_btn.pack_forget()

        self.status_var.set(f"อัปโหลดเสร็จ — {success_count}/{total}")

    # -----------------------------------------------------------------------
    # Settings Tab
    # -----------------------------------------------------------------------

    def _build_settings_tab(self):
        tab = self.tab_settings

        # Scrollable container for settings
        settings_scroll = ctk.CTkScrollableFrame(tab)
        settings_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # --- Setup Wizard button ---
        wizard_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        wizard_frame.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkButton(
            wizard_frame, text="Setup Wizard", width=160,
            font=self._font(14, "bold"), fg_color="#8e44ad",
            hover_color="#6c3483", command=self._open_setup_wizard,
        ).pack(side="left")
        ctk.CTkLabel(wizard_frame, text="คู่มือตั้งค่า API ทีละขั้นตอน",
                      font=self._font(12), text_color="gray").pack(side="left", padx=(10, 0))

        # Section header — API Keys
        ctk.CTkLabel(settings_scroll, text="API Keys", font=self._font(16, "bold")).pack(
            anchor="w", padx=12, pady=(12, 8)
        )

        # --- KIE_API_KEY ---
        kie_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        kie_frame.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(kie_frame, text="Kie.ai API Key:", font=self._font(13), width=140, anchor="w").pack(side="left")

        self._kie_key_var = ctk.StringVar(value=os.environ.get("KIE_API_KEY", ""))
        self._kie_key_entry = ctk.CTkEntry(kie_frame, textvariable=self._kie_key_var, width=380, font=self._font(13), show="*")
        self._kie_key_entry.pack(side="left", padx=(0, 4))

        self._kie_show = False
        self._kie_toggle_btn = ctk.CTkButton(
            kie_frame, text="แสดง", width=60, font=self._font(12),
            command=self._toggle_kie_visibility,
        )
        self._kie_toggle_btn.pack(side="left")

        # --- GEMINI_API_KEY ---
        gemini_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        gemini_frame.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(gemini_frame, text="Gemini API Key:", font=self._font(13), width=140, anchor="w").pack(side="left")

        self._gemini_key_var = ctk.StringVar(value=os.environ.get("GEMINI_API_KEY", ""))
        self._gemini_key_entry = ctk.CTkEntry(gemini_frame, textvariable=self._gemini_key_var, width=380, font=self._font(13), show="*")
        self._gemini_key_entry.pack(side="left", padx=(0, 4))

        self._gemini_show = False
        self._gemini_toggle_btn = ctk.CTkButton(
            gemini_frame, text="แสดง", width=60, font=self._font(12),
            command=self._toggle_gemini_visibility,
        )
        self._gemini_toggle_btn.pack(side="left")

        # --- Upload API Settings ---
        ctk.CTkLabel(settings_scroll, text="Upload API", font=self._font(16, "bold")).pack(
            anchor="w", padx=12, pady=(16, 8)
        )

        # ---- YouTube ----
        yt_box = ctk.CTkFrame(settings_scroll)
        yt_box.pack(fill="x", padx=12, pady=(0, 8))

        yt_header = ctk.CTkFrame(yt_box, fg_color="transparent")
        yt_header.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(yt_header, text="YouTube", font=self._font(14, "bold")).pack(side="left")
        self._yt_settings_status = ctk.CTkLabel(yt_header, text="", font=self._font(11))
        self._yt_settings_status.pack(side="right")

        yt_row = ctk.CTkFrame(yt_box, fg_color="transparent")
        yt_row.pack(fill="x", padx=8, pady=(0, 6))

        self._yt_file_label = ctk.CTkLabel(yt_row, text="", font=self._font(12), anchor="w")
        self._yt_file_label.pack(side="left")
        self._update_yt_file_status()

        ctk.CTkButton(yt_row, text="เลือกไฟล์...", width=90, font=self._font(12),
                       command=self._browse_youtube_secrets).pack(side="left", padx=(8, 4))
        ctk.CTkButton(yt_row, text="Google Console", width=110, font=self._font(12),
                       fg_color="transparent", text_color="#3498db",
                       hover_color=("gray85", "gray30"),
                       command=lambda: webbrowser.open(
                           "https://console.cloud.google.com/apis/credentials")
                       ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(yt_row, text="ทดสอบ", width=70, font=self._font(12),
                       fg_color="#27ae60", hover_color="#1e8449",
                       command=self._test_youtube).pack(side="right")

        # ---- TikTok (Browser Automation) ----
        tt_box = ctk.CTkFrame(settings_scroll)
        tt_box.pack(fill="x", padx=12, pady=(0, 8))

        tt_header = ctk.CTkFrame(tt_box, fg_color="transparent")
        tt_header.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(tt_header, text="TikTok", font=self._font(14, "bold")).pack(side="left")
        ctk.CTkLabel(tt_header, text="(Browser — login ครั้งเดียว)",
                      font=self._font(11), text_color="#3498db").pack(side="left", padx=(6, 0))
        self._tt_settings_status = ctk.CTkLabel(tt_header, text="", font=self._font(11))
        self._tt_settings_status.pack(side="right")

        tt_desc_row = ctk.CTkFrame(tt_box, fg_color="transparent")
        tt_desc_row.pack(fill="x", padx=8, pady=(2, 4))
        ctk.CTkLabel(tt_desc_row,
                      text="Login TikTok ผ่านเบราว์เซอร์ครั้งเดียว แล้วอัปโหลดอัตโนมัติได้เลย",
                      font=self._font(12), text_color="gray", wraplength=500,
                      justify="left").pack(anchor="w")

        tt_btn_frame = ctk.CTkFrame(tt_box, fg_color="transparent")
        tt_btn_frame.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkButton(tt_btn_frame, text="Login TikTok", width=160,
                       font=self._font(13, "bold"), fg_color="#e1306c", hover_color="#c2185b",
                       command=self._tiktok_browser_login).pack(side="left")
        ctk.CTkButton(tt_btn_frame, text="ล้าง Cookie", width=100, font=self._font(12),
                       fg_color="transparent", text_color="#e74c3c",
                       hover_color=("gray85", "gray30"),
                       command=self._tiktok_clear_cookies).pack(side="left", padx=(8, 0))

        self._tt_cookie_status = ctk.CTkLabel(tt_box, text="", font=self._font(12))
        self._tt_cookie_status.pack(anchor="w", padx=8, pady=(0, 6))
        self._update_tiktok_cookie_status()

        # ---- Facebook ----
        saved = load_settings()
        fb_box = ctk.CTkFrame(settings_scroll)
        fb_box.pack(fill="x", padx=12, pady=(0, 8))

        fb_header = ctk.CTkFrame(fb_box, fg_color="transparent")
        fb_header.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(fb_header, text="Facebook Reels", font=self._font(14, "bold")).pack(side="left")
        self._fb_settings_status = ctk.CTkLabel(fb_header, text="", font=self._font(11))
        self._fb_settings_status.pack(side="right")

        fb_tok_frame = ctk.CTkFrame(fb_box, fg_color="transparent")
        fb_tok_frame.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkLabel(fb_tok_frame, text="Access Token:", font=self._font(13), width=120, anchor="w").pack(side="left")
        self._fb_token_var = ctk.StringVar(value=saved.get("facebook_access_token", ""))
        ctk.CTkEntry(fb_tok_frame, textvariable=self._fb_token_var, width=350, font=self._font(13), show="*").pack(side="left")

        fb_id_frame = ctk.CTkFrame(fb_box, fg_color="transparent")
        fb_id_frame.pack(fill="x", padx=8, pady=(0, 3))
        ctk.CTkLabel(fb_id_frame, text="Page ID:", font=self._font(13), width=120, anchor="w").pack(side="left")
        self._fb_page_id_var = ctk.StringVar(value=saved.get("facebook_page_id", ""))
        ctk.CTkEntry(fb_id_frame, textvariable=self._fb_page_id_var, width=350, font=self._font(13),
                      placeholder_text="ไม่ใส่ = โปรไฟล์ส่วนตัว").pack(side="left")

        fb_btn_frame = ctk.CTkFrame(fb_box, fg_color="transparent")
        fb_btn_frame.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkButton(fb_btn_frame, text="Graph API Explorer", width=140, font=self._font(12),
                       fg_color="transparent", text_color="#3498db",
                       hover_color=("gray85", "gray30"),
                       command=lambda: webbrowser.open(
                           "https://developers.facebook.com/tools/explorer/")
                       ).pack(side="left")
        ctk.CTkButton(fb_btn_frame, text="ทดสอบ", width=70, font=self._font(12),
                       fg_color="#27ae60", hover_color="#1e8449",
                       command=self._test_facebook).pack(side="right")

        # --- Save button + status ---
        save_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        save_frame.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkButton(
            save_frame, text="บันทึก", width=120, font=self._font(14, "bold"),
            command=self._on_save_settings,
        ).pack(side="left")

        self._settings_status = ctk.CTkLabel(save_frame, text="", font=self._font(13))
        self._settings_status.pack(side="left", padx=(12, 0))

    def _toggle_kie_visibility(self):
        self._kie_show = not self._kie_show
        self._kie_key_entry.configure(show="" if self._kie_show else "*")
        self._kie_toggle_btn.configure(text="ซ่อน" if self._kie_show else "แสดง")

    def _toggle_gemini_visibility(self):
        self._gemini_show = not self._gemini_show
        self._gemini_key_entry.configure(show="" if self._gemini_show else "*")
        self._gemini_toggle_btn.configure(text="ซ่อน" if self._gemini_show else "แสดง")

    # --- YouTube file browse ---

    def _update_yt_file_status(self):
        """Update YouTube client_secrets.json status label."""
        if os.path.exists("client_secrets.json"):
            try:
                with open("client_secrets.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Validate structure
                if "installed" in data or "web" in data:
                    self._yt_file_label.configure(
                        text="client_secrets.json (OK)",
                        text_color="#2ecc71")
                else:
                    self._yt_file_label.configure(
                        text="client_secrets.json (รูปแบบไม่ถูกต้อง)",
                        text_color="#e74c3c")
            except (json.JSONDecodeError, OSError):
                self._yt_file_label.configure(
                    text="client_secrets.json (อ่านไม่ได้)",
                    text_color="#e74c3c")
        else:
            self._yt_file_label.configure(
                text="ยังไม่มี client_secrets.json",
                text_color="#e67e22")

    def _browse_youtube_secrets(self):
        """Open file dialog to select client_secrets.json and copy it to project folder."""
        import shutil
        filepath = tkfiledialog.askopenfilename(
            title="เลือก client_secrets.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filepath:
            return

        # Validate the file
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "installed" not in data and "web" not in data:
                tkmessagebox.showerror(
                    "รูปแบบไม่ถูกต้อง",
                    "ไฟล์นี้ไม่ใช่ OAuth 2.0 Client Secret\n\n"
                    "ต้องมี key 'installed' หรือ 'web'\n"
                    "ดาวน์โหลดจาก Google Cloud Console > Credentials > OAuth 2.0 Client IDs")
                return
        except (json.JSONDecodeError, OSError) as e:
            tkmessagebox.showerror("อ่านไฟล์ไม่ได้", str(e))
            return

        # Copy to project folder
        dest = os.path.join(_base_dir, "client_secrets.json")
        try:
            shutil.copy2(filepath, dest)
            self._update_yt_file_status()
            self._update_platform_status()
            self._yt_settings_status.configure(text="คัดลอกไฟล์แล้ว", text_color="#2ecc71")
        except OSError as e:
            tkmessagebox.showerror("คัดลอกไม่ได้", str(e))

    # --- Test Connection buttons ---

    def _test_youtube(self):
        """Test YouTube OAuth2 connection."""
        self._yt_settings_status.configure(text="กำลังทดสอบ...", text_color="#f39c12")
        self.update_idletasks()

        if not os.path.exists("client_secrets.json"):
            self._yt_settings_status.configure(
                text="ไม่พบ client_secrets.json", text_color="#e74c3c")
            return

        # Validate file format
        try:
            with open("client_secrets.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            if "installed" not in data and "web" not in data:
                self._yt_settings_status.configure(
                    text="รูปแบบไฟล์ไม่ถูกต้อง", text_color="#e74c3c")
                return
        except (json.JSONDecodeError, OSError):
            self._yt_settings_status.configure(
                text="อ่านไฟล์ไม่ได้", text_color="#e74c3c")
            return

        def task():
            yt = YouTubeUploader()
            ok = yt.authenticate()
            def done():
                if ok:
                    self._yt_settings_status.configure(
                        text="เชื่อมต่อ YouTube สำเร็จ!", text_color="#2ecc71")
                else:
                    self._yt_settings_status.configure(
                        text="เชื่อมต่อไม่สำเร็จ", text_color="#e74c3c")
                self._update_platform_status()
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _tiktok_browser_login(self):
        """Open browser for TikTok login, save cookies."""
        self._tt_settings_status.configure(text="กำลังเปิดเบราว์เซอร์...", text_color="#f39c12")
        self._tt_cookie_status.configure(text="กรุณา login ในเบราว์เซอร์ที่เปิดขึ้นมา...", text_color="#f39c12")
        self.update_idletasks()

        def task():
            tt = TikTokBrowserUploader()
            ok = tt.login()
            def done():
                if ok:
                    self._tt_settings_status.configure(
                        text="Login TikTok สำเร็จ!", text_color="#2ecc71")
                else:
                    self._tt_settings_status.configure(
                        text="Login ไม่สำเร็จ — ลองใหม่", text_color="#e74c3c")
                self._update_tiktok_cookie_status()
                self._update_platform_status()
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _tiktok_clear_cookies(self):
        """Delete TikTok cookies for re-login."""
        tt = TikTokBrowserUploader()
        tt.clear_cookies()
        self._tt_settings_status.configure(text="ลบ cookie แล้ว", text_color="#f39c12")
        self._update_tiktok_cookie_status()
        self._update_platform_status()

    def _update_tiktok_cookie_status(self):
        """Update the TikTok cookie status label."""
        tt = TikTokBrowserUploader()
        if tt.is_configured():
            self._tt_cookie_status.configure(
                text="พร้อม (cookie saved)", text_color="#2ecc71")
        else:
            self._tt_cookie_status.configure(
                text="ยังไม่ได้ login", text_color="#e67e22")

    def _test_facebook(self):
        """Test Facebook access token."""
        page_id = self._fb_page_id_var.get().strip()
        token = self._fb_token_var.get().strip()

        if not token:
            self._fb_settings_status.configure(
                text="กรุณากรอก Access Token ก่อน", text_color="#e74c3c")
            return

        # Save credentials first
        s = load_settings()
        s["facebook_page_id"] = page_id
        s["facebook_access_token"] = token
        save_settings(s)

        self._fb_settings_status.configure(text="กำลังทดสอบ...", text_color="#f39c12")
        self.update_idletasks()

        def task():
            fb = FacebookUploader(page_id=page_id, access_token=token)
            ok = fb.is_authenticated()
            def done():
                if ok:
                    self._fb_settings_status.configure(
                        text="เชื่อมต่อ Facebook สำเร็จ!", text_color="#2ecc71")
                else:
                    self._fb_settings_status.configure(
                        text="Token ไม่ถูกต้อง/หมดอายุ", text_color="#e74c3c")
                self._update_platform_status()
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # --- Setup Wizard ---

    def _open_setup_wizard(self):
        """Open a step-by-step wizard dialog for setting up upload credentials."""
        wizard = ctk.CTkToplevel(self)
        wizard.title("Setup Wizard — ตั้งค่าอัปโหลด")
        wizard.geometry("620x520")
        wizard.resizable(False, False)
        wizard.transient(self)
        wizard.grab_set()

        # Center on parent
        wizard.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 620) // 2
        y = self.winfo_y() + (self.winfo_height() - 520) // 2
        wizard.geometry(f"+{x}+{y}")

        # State
        wizard._step = 0
        steps = ["YouTube", "TikTok", "Facebook", "เสร็จสิ้น"]

        # Header with step indicator
        header_frame = ctk.CTkFrame(wizard, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        step_labels = []
        for i, name in enumerate(steps):
            lbl = ctk.CTkLabel(header_frame, text=f"{i+1}. {name}",
                               font=self._font(13), text_color="gray")
            lbl.pack(side="left", padx=(0, 16))
            step_labels.append(lbl)

        # Content area
        content = ctk.CTkFrame(wizard)
        content.pack(fill="both", expand=True, padx=16, pady=8)

        # Navigation
        nav = ctk.CTkFrame(wizard, fg_color="transparent")
        nav.pack(fill="x", padx=16, pady=(4, 12))

        skip_btn = ctk.CTkButton(nav, text="ข้าม", width=80, font=self._font(13),
                                  fg_color="transparent", text_color="gray",
                                  hover_color=("gray85", "gray30"))
        skip_btn.pack(side="left")

        done_btn = ctk.CTkButton(nav, text="ถัดไป", width=100, font=self._font(14, "bold"))
        done_btn.pack(side="right")

        back_btn = ctk.CTkButton(nav, text="ก่อนหน้า", width=80, font=self._font(13),
                                  fg_color="transparent", text_color="#3498db",
                                  hover_color=("gray85", "gray30"))
        back_btn.pack(side="right", padx=(0, 8))

        def show_step(step_idx):
            wizard._step = step_idx
            # Update step indicator
            for i, lbl in enumerate(step_labels):
                if i == step_idx:
                    lbl.configure(text_color="#3498db", font=self._font(13, "bold"))
                elif i < step_idx:
                    lbl.configure(text_color="#2ecc71", font=self._font(13))
                else:
                    lbl.configure(text_color="gray", font=self._font(13))

            # Clear content
            for w in content.winfo_children():
                w.destroy()

            # Navigation state
            back_btn.configure(state="normal" if step_idx > 0 else "disabled")
            if step_idx < len(steps) - 1:
                done_btn.configure(text="ถัดไป")
                skip_btn.pack(side="left")
            else:
                done_btn.configure(text="ปิด")
                skip_btn.pack_forget()

            if step_idx == 0:
                self._wizard_youtube(content)
            elif step_idx == 1:
                self._wizard_tiktok(content)
            elif step_idx == 2:
                self._wizard_facebook(content)
            elif step_idx == 3:
                self._wizard_done(content)

        def next_step():
            if wizard._step >= len(steps) - 1:
                wizard.destroy()
                self._update_platform_status()
                return
            show_step(wizard._step + 1)

        def prev_step():
            if wizard._step > 0:
                show_step(wizard._step - 1)

        skip_btn.configure(command=next_step)
        done_btn.configure(command=next_step)
        back_btn.configure(command=prev_step)

        show_step(0)

    def _wizard_youtube(self, parent):
        """YouTube setup step content."""
        ctk.CTkLabel(parent, text="YouTube Shorts", font=self._font(18, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        instructions = (
            "1. ไปที่ Google Cloud Console\n"
            "2. สร้าง Project ใหม่ (หรือเลือก Project ที่มี)\n"
            "3. เปิด YouTube Data API v3\n"
            "4. ไปที่ Credentials > Create Credentials > OAuth Client ID\n"
            "5. เลือก Application Type: Desktop App\n"
            "6. ดาวน์โหลดไฟล์ JSON แล้วเลือกด้านล่าง"
        )
        ctk.CTkLabel(parent, text=instructions, font=self._font(12),
                      justify="left", wraplength=560).pack(
            anchor="w", padx=12, pady=(0, 8))

        # Link to console
        ctk.CTkButton(parent, text="เปิด Google Cloud Console",
                       font=self._font(13), width=220,
                       command=lambda: webbrowser.open(
                           "https://console.cloud.google.com/apis/credentials")
                       ).pack(anchor="w", padx=12, pady=(0, 8))

        # File status + browse
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(fill="x", padx=12, pady=4)

        status_text = "client_secrets.json"
        if os.path.exists("client_secrets.json"):
            status_color = "#2ecc71"
            status_text += " (พบแล้ว)"
        else:
            status_color = "#e67e22"
            status_text += " (ยังไม่มี)"
        wiz_yt_lbl = ctk.CTkLabel(file_frame, text=status_text,
                                    font=self._font(13), text_color=status_color)
        wiz_yt_lbl.pack(side="left")

        def browse_and_update():
            self._browse_youtube_secrets()
            if os.path.exists("client_secrets.json"):
                wiz_yt_lbl.configure(text="client_secrets.json (พบแล้ว)",
                                      text_color="#2ecc71")

        ctk.CTkButton(file_frame, text="เลือกไฟล์...", width=100, font=self._font(12),
                       command=browse_and_update).pack(side="left", padx=(10, 0))

    def _wizard_tiktok(self, parent):
        """TikTok setup step content — browser login."""
        ctk.CTkLabel(parent, text="TikTok", font=self._font(18, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        # Description
        ctk.CTkLabel(parent,
                      text="Login TikTok ผ่านเบราว์เซอร์ครั้งเดียว\n"
                           "ระบบจะจำ cookie ไว้ แล้วอัปโหลดอัตโนมัติได้เลย",
                      font=self._font(13), justify="left", wraplength=540).pack(
            anchor="w", padx=12, pady=(0, 10))

        # Cookie status
        tt = TikTokBrowserUploader()
        wiz_tt_status = ctk.CTkLabel(parent, text="", font=self._font(12))
        wiz_tt_status.pack(anchor="w", padx=12, pady=(0, 6))
        if tt.is_configured():
            wiz_tt_status.configure(text="พร้อม (cookie saved)", text_color="#2ecc71")
        else:
            wiz_tt_status.configure(text="ยังไม่ได้ login", text_color="#e67e22")

        # Login button
        def on_wizard_login():
            wiz_tt_status.configure(text="กำลังเปิดเบราว์เซอร์...", text_color="#f39c12")
            parent.update_idletasks()
            def task():
                browser_tt = TikTokBrowserUploader()
                ok = browser_tt.login()
                def done():
                    if ok:
                        wiz_tt_status.configure(text="Login สำเร็จ! (cookie saved)", text_color="#2ecc71")
                    else:
                        wiz_tt_status.configure(text="Login ไม่สำเร็จ — ลองใหม่", text_color="#e74c3c")
                    self._update_platform_status()
                    try:
                        self._update_tiktok_cookie_status()
                    except Exception:
                        pass
                self.after(0, done)
            threading.Thread(target=task, daemon=True).start()

        ctk.CTkButton(parent, text="Login TikTok", width=200,
                       font=self._font(14, "bold"), fg_color="#e1306c", hover_color="#c2185b",
                       command=on_wizard_login).pack(anchor="w", padx=12, pady=(0, 10))

        # Instructions
        instructions = (
            "วิธีใช้:\n"
            "1. กด 'Login TikTok' — เบราว์เซอร์ Edge จะเปิดขึ้น\n"
            "2. Login ด้วยบัญชี TikTok ของคุณ\n"
            "3. เมื่อ login สำเร็จ เบราว์เซอร์จะปิดอัตโนมัติ\n"
            "4. Cookie จะถูกบันทึกไว้ใช้อัปโหลดครั้งต่อไป"
        )
        ctk.CTkLabel(parent, text=instructions, font=self._font(11),
                      justify="left", wraplength=560, text_color="gray").pack(
            anchor="w", padx=12, pady=(0, 6))

    def _wizard_facebook(self, parent):
        """Facebook setup step content."""
        ctk.CTkLabel(parent, text="Facebook Reels", font=self._font(18, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        instructions = (
            "1. ไปที่ developers.facebook.com > สร้าง App\n"
            "2. เพิ่ม Facebook Login product\n"
            "3. ไปที่ Graph API Explorer\n"
            "4. เลือก permission: publish_video\n"
            "   (เพิ่ม pages_manage_posts ถ้าจะโพสต์ลง Page)\n"
            "5. สร้าง Access Token แล้วแปลงเป็น Long-Lived Token\n"
            "6. คัดลอก Access Token มาวางด้านล่าง"
        )
        ctk.CTkLabel(parent, text=instructions, font=self._font(12),
                      justify="left", wraplength=560).pack(
            anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(parent, text="เปิด Graph API Explorer",
                       font=self._font(13), width=220,
                       command=lambda: webbrowser.open(
                           "https://developers.facebook.com/tools/explorer/")
                       ).pack(anchor="w", padx=12, pady=(0, 8))

        # Input fields — Token first (required), Page ID optional

        tok_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tok_frame.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(tok_frame, text="Access Token:", font=self._font(13),
                      width=110, anchor="w").pack(side="left")
        ctk.CTkEntry(tok_frame, textvariable=self._fb_token_var,
                      width=380, font=self._font(13), show="*").pack(side="left")

        id_frame = ctk.CTkFrame(parent, fg_color="transparent")
        id_frame.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(id_frame, text="Page ID:", font=self._font(13),
                      width=110, anchor="w").pack(side="left")
        ctk.CTkEntry(id_frame, textvariable=self._fb_page_id_var,
                      width=280, font=self._font(13),
                      placeholder_text="ไม่ใส่ = โปรไฟล์ส่วนตัว").pack(side="left")
        ctk.CTkLabel(id_frame, text="(optional)", font=self._font(11),
                      text_color="gray").pack(side="left", padx=(6, 0))

    def _wizard_done(self, parent):
        """Summary step — show what's configured."""
        ctk.CTkLabel(parent, text="ตั้งค่าเสร็จสิ้น!", font=self._font(18, "bold")).pack(
            anchor="w", padx=12, pady=(10, 8))

        # Check each platform
        checks = []

        yt = YouTubeUploader()
        if yt.is_configured():
            checks.append(("YouTube", True, "client_secrets.json พร้อม"))
        else:
            checks.append(("YouTube", False, "ยังไม่มี client_secrets.json"))

        tt_browser = TikTokBrowserUploader()
        if tt_browser.is_configured():
            checks.append(("TikTok", True, "Cookie พร้อม — login แล้ว"))
        else:
            checks.append(("TikTok", False, "ยังไม่ได้ login"))

        fb_tok = self._fb_token_var.get().strip()
        fb_id = self._fb_page_id_var.get().strip()
        if fb_tok:
            target = f"Page: {fb_id}" if fb_id else "โปรไฟล์ส่วนตัว"
            checks.append(("Facebook", True, f"Token พร้อม ({target})"))
        else:
            checks.append(("Facebook", False, "ยังไม่ได้ตั้งค่า Access Token"))

        for name, ok, desc in checks:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            icon = "[OK]" if ok else "[--]"
            color = "#2ecc71" if ok else "#e67e22"
            ctk.CTkLabel(row, text=f"{icon} {name}", font=self._font(14, "bold"),
                          text_color=color, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=desc, font=self._font(12),
                          text_color="gray").pack(side="left")

        configured = sum(1 for _, ok, _ in checks if ok)
        ctk.CTkLabel(parent,
                      text=f"\nตั้งค่าแล้ว {configured}/3 แพลตฟอร์ม\n"
                           f"กด 'บันทึก' ในหน้าตั้งค่าเพื่อบันทึก credentials\n"
                           f"แล้วกด 'ทดสอบ' เพื่อตรวจสอบการเชื่อมต่อ",
                      font=self._font(13), justify="left", wraplength=560).pack(
            anchor="w", padx=12, pady=(12, 0))

    def _on_save_settings(self):
        # Save API keys to .env
        keys = {
            "KIE_API_KEY": self._kie_key_var.get().strip(),
            "GEMINI_API_KEY": self._gemini_key_var.get().strip(),
        }
        try:
            self._save_env(keys)
            for k, v in keys.items():
                os.environ[k] = v
        except Exception as e:
            self._settings_status.configure(text=f"ผิดพลาด: {e}", text_color="#e74c3c")
            return

        # Save upload credentials to settings.json
        s = load_settings()
        s["facebook_page_id"] = self._fb_page_id_var.get().strip()
        s["facebook_access_token"] = self._fb_token_var.get().strip()
        save_settings(s)

        self._settings_status.configure(text="บันทึกแล้ว", text_color="#2ecc71")
        # Refresh upload tab status
        self._update_platform_status()

    @staticmethod
    def _save_env(updates: dict):
        """Read .env, update matching keys (or append new), write back."""
        lines: list[str] = []
        found_keys: set[str] = set()

        if os.path.exists(_env_path):
            with open(_env_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    stripped = raw_line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        key = stripped.split("=", 1)[0].strip()
                        if key in updates:
                            lines.append(f"{key}={updates[key]}\n")
                            found_keys.add(key)
                            continue
                    lines.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")

        # Append keys that weren't found in existing file
        for key, value in updates.items():
            if key not in found_keys:
                lines.append(f"{key}={value}\n")

        with open(_env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = HookToShortApp()
    app.mainloop()
