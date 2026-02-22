"""
Hook-to-Short — CustomTkinter Desktop UI
ดาวน์โหลดเพลงจาก YouTube, ตัดท่อนฮุก, ตรวจอารมณ์, สร้างภาพปก, ตัดต่อวิดีโอสั้น
"""

import os
import sys
import json
import logging
import subprocess
import threading
import warnings
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
from PIL import Image as PILImage

# Monkey-patch: soundfile 0.13+ removed SoundFileRuntimeError but librosa still expects it
import soundfile as _sf
if not hasattr(_sf, 'SoundFileRuntimeError'):
    _sf.SoundFileRuntimeError = RuntimeError

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from python.mood_detector import MoodDetector, extract_metadata_from_title
from python.kie_generator import KieAIGenerator
from python.video_composer import VideoComposer, compose_complete_short

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DOWNLOADS_FOLDER = "./downloads"
OUTPUTS_FOLDER = "./outputs"
TRACKS_DB = "tracks.json"

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


def _cleanup_temp_hooks():
    """Remove leftover _tmp_hook_*.wav files from outputs."""
    for f in glob_mod.glob(os.path.join(OUTPUTS_FOLDER, "_tmp_hook_*.wav")):
        try:
            os.remove(f)
            logger.info(f"Cleaned up temp file: {os.path.basename(f)}")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class HookToShortApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Clean up leftover temp files on startup
        _cleanup_temp_hooks()

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

        self._build_download_tab()
        self._build_library_tab()
        self._build_create_tab()

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

    def _on_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.dl_progress.configure(text="กรุณาใส่ลิงก์ YouTube")
            return

        self.download_btn.configure(state="disabled")
        self.dl_result_frame.pack_forget()
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
                final_path = os.path.join(DOWNLOADS_FOLDER, mp3_file)
                os.replace(os.path.join(temp_folder, mp3_file), final_path)

                file_size = os.path.getsize(final_path) / (1024 * 1024)

                track_info = {
                    "title": song_title,
                    "youtube_url": url,
                    "file_path": final_path,
                    "filename": mp3_file,
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

        self.lib_scroll = ctk.CTkScrollableFrame(tab)
        self.lib_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._refresh_library()

    def _refresh_library(self):
        for widget in self.lib_scroll.winfo_children():
            widget.destroy()

        tracks = load_tracks()
        self.lib_count_label.configure(text=f"เพลง: {len(tracks)} เพลง")

        if not tracks:
            ctk.CTkLabel(self.lib_scroll, text="ยังไม่มีเพลง ลองดาวน์โหลดเพลงก่อน!",
                         font=self._font(13)).pack(pady=20)
            return

        for track in tracks:
            row = ctk.CTkFrame(self.lib_scroll)
            row.pack(fill="x", pady=2)

            info = (
                f"{track.get('title', '?')}  |  "
                f"{track.get('artist', 'ไม่ทราบ')}  |  "
                f"{track.get('filename', '')}  |  "
                f"{track.get('file_size_mb', '?')} MB  |  "
                f"{track.get('created_at', '')[:10]}"
            )
            ctk.CTkLabel(row, text=info, anchor="w", font=self._font(13)).pack(side="left", fill="x", expand=True, padx=6, pady=4)

            track_id = track.get("id")
            del_btn = ctk.CTkButton(
                row, text="ลบ", width=60, fg_color="#c0392b", hover_color="#e74c3c",
                font=self._font(13),
                command=lambda tid=track_id: self._delete_track(tid),
            )
            del_btn.pack(side="right", padx=4, pady=4)

    def _delete_track(self, track_id):
        tracks = load_tracks()
        tracks = [t for t in tracks if t.get("id") != track_id]
        save_tracks(tracks)
        self._refresh_library()
        self._refresh_track_dropdown()
        self.status_var.set(f"ลบเพลง #{track_id} แล้ว")

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

        # Generate button
        self.generate_btn = ctk.CTkButton(tab, text="สร้างวิดีโอสั้น", width=180, font=self._font(14, "bold"), command=self._on_generate)
        self.generate_btn.pack(pady=(8, 4))

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
                self._gen_step("ขั้น 4/6  สร้างภาพปกด้วย AI (Kie.ai)...")
                gen = KieAIGenerator()
                art_filename = f"{song_title.replace(' ', '_')}_art.png"
                art_path = os.path.join(OUTPUTS_FOLDER, art_filename)
                image_path = gen.generate_album_art(
                    song_title=song_title,
                    mood=mood,
                    intensity=intensity,
                    output_path=art_path,
                    video_style=video_style,
                    font_style=font_style,
                    font_angle=font_angle,
                    artist=artist,
                )
                if not image_path:
                    self.after(0, lambda: self._gen_done(None, "สร้างภาพปกไม่สำเร็จ"))
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = HookToShortApp()
    app.mainloop()
