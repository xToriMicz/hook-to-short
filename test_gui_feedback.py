"""
GUI feedback integration tests — verify label/progress text for each URL type.

Tests the full path: URL -> _classify_url() -> handler -> label text,
without requiring a display (pure logic verification).
"""
import re
from urllib.parse import urlparse, parse_qs


# ---------------------------------------------------------------------------
# Mirror of HookToShortApp._classify_url()
# ---------------------------------------------------------------------------
def _classify_url(url: str):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    path = parsed.path.rstrip('/')

    if path == '/playlist' and 'list' in qs:
        return ("playlist", url)

    if '/watch' in path and 'v' in qs:
        if 'list' in qs:
            return ("playlist", url)
        return ("video", url)

    if parsed.hostname in ('youtu.be', 'www.youtu.be'):
        if 'list' in qs:
            return ("playlist", url)
        return ("video", url)

    if re.search(r'/shorts/[A-Za-z0-9_-]+$', path):
        return ("video", url)

    if re.search(r'/live/[A-Za-z0-9_-]+$', path):
        return ("video", url)

    if re.search(r'/@[^/]+/releases$', path):
        return ("releases", url)

    if re.search(r'/@[^/]+/videos$', path):
        return ("channel", url)
    if re.search(r'/(c/[^/]+|channel/[^/]+)/videos$', path):
        return ("channel", url)

    if re.search(r'/@[^/]+$', path) or re.search(r'/(c|channel)/[^/]+$', path):
        return ("channel", url.rstrip('/') + '/videos')

    return ("channel", url.rstrip('/') + '/videos')


# ---------------------------------------------------------------------------
# Mirror of _on_scan_channel() label logic
# ---------------------------------------------------------------------------
TYPE_LABELS = {
    "playlist": "Playlist",
    "releases": "Releases",
    "channel": "Channel",
}


def get_scan_feedback(url: str) -> str:
    """Simulate pasting a URL in the batch scanner and return the feedback text."""
    url_type, clean_url = _classify_url(url)

    if url_type == "video":
        return "ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน"

    type_label = TYPE_LABELS.get(url_type, url_type)
    return f"กำลังสแกน {type_label} (สูงสุด 50 คลิป)..."


def get_download_feedback(url: str) -> str:
    """Simulate pasting a URL in the single-video download field.

    Returns the *initial* feedback text before the background download starts.
    """
    if 'list=' in url:
        return "[มี playlist — ใช้สแกนด้านล่าง] กำลังดาวน์โหลดเฉพาะคลิปนี้..."
    return "กำลังดาวน์โหลด... อาจใช้เวลาสักครู่"


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# (url, expected_scan_feedback, expected_download_feedback, label)
SCAN_TESTS = [
    # --- Videos -> should redirect to single-download field ---
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ",
     "ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน",
     "standard video in scanner -> redirect"),

    ("https://youtu.be/dQw4w9WgXcQ",
     "ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน",
     "youtu.be in scanner -> redirect"),

    ("https://www.youtube.com/shorts/abcDEF12345",
     "ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน",
     "shorts URL in scanner -> redirect"),

    ("https://www.youtube.com/live/abcDEF12345",
     "ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน",
     "live URL in scanner -> redirect"),

    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ",
     "ลิงก์นี้เป็นวิดีโอเดี่ยว ใช้ช่องดาวน์โหลดด้านบนแทน",
     "YouTube Music video in scanner -> redirect"),

    # --- Playlists -> should start scanning ---
    ("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "กำลังสแกน Playlist (สูงสุด 50 คลิป)...",
     "standard playlist -> scan Playlist"),

    ("https://www.youtube.com/watch?v=abc123&list=OLAK5uy_abc123",
     "กำลังสแกน Playlist (สูงสุด 50 คลิป)...",
     "watch with list param -> scan Playlist"),

    ("https://music.youtube.com/playlist?list=OLAK5uy_abc123",
     "กำลังสแกน Playlist (สูงสุด 50 คลิป)...",
     "YouTube Music playlist -> scan Playlist"),

    ("https://youtu.be/dQw4w9WgXcQ?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "กำลังสแกน Playlist (สูงสุด 50 คลิป)...",
     "youtu.be with list -> scan Playlist"),

    ("https://music.youtube.com/watch?v=abc&list=RDCLAK5uy_abc",
     "กำลังสแกน Playlist (สูงสุด 50 คลิป)...",
     "YouTube Music radio/mix -> scan Playlist"),

    # --- Channels -> should start scanning ---
    ("https://www.youtube.com/@LosgaBb",
     "กำลังสแกน Channel (สูงสุด 50 คลิป)...",
     "bare @channel -> scan Channel"),

    ("https://www.youtube.com/@LosgaBb/videos",
     "กำลังสแกน Channel (สูงสุด 50 คลิป)...",
     "@channel/videos -> scan Channel"),

    ("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
     "กำลังสแกน Channel (สูงสุด 50 คลิป)...",
     "channel ID (no @) -> scan Channel"),

    ("https://www.youtube.com/c/SomeChannel",
     "กำลังสแกน Channel (สูงสุด 50 คลิป)...",
     "/c/ custom URL -> scan Channel"),

    # --- Releases -> should start scanning ---
    ("https://www.youtube.com/@LosgaBb/releases",
     "กำลังสแกน Releases (สูงสุด 50 คลิป)...",
     "@channel/releases -> scan Releases"),
]

# Separate test for single-download field feedback
DOWNLOAD_TESTS = [
    # --- Normal videos: no warning ---
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ",
     "กำลังดาวน์โหลด... อาจใช้เวลาสักครู่",
     "standard video -> download"),

    ("https://youtu.be/dQw4w9WgXcQ",
     "กำลังดาวน์โหลด... อาจใช้เวลาสักครู่",
     "youtu.be -> download"),

    ("https://www.youtube.com/shorts/abcDEF12345",
     "กำลังดาวน์โหลด... อาจใช้เวลาสักครู่",
     "shorts -> download"),

    ("https://www.youtube.com/live/abcDEF12345",
     "กำลังดาวน์โหลด... อาจใช้เวลาสักครู่",
     "live -> download"),

    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ",
     "กำลังดาวน์โหลด... อาจใช้เวลาสักครู่",
     "YouTube Music single -> download"),

    # --- URLs with list= : should warn (prepended to progress) ---
    ("https://www.youtube.com/watch?v=abc123&list=OLAK5uy_abc123",
     "[มี playlist — ใช้สแกนด้านล่าง] กำลังดาวน์โหลดเฉพาะคลิปนี้...",
     "watch with list= -> playlist warning"),

    ("https://youtu.be/dQw4w9WgXcQ?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "[มี playlist — ใช้สแกนด้านล่าง] กำลังดาวน์โหลดเฉพาะคลิปนี้...",
     "youtu.be with list= -> playlist warning"),

    ("https://music.youtube.com/watch?v=abc&list=RDCLAK5uy_abc",
     "[มี playlist — ใช้สแกนด้านล่าง] กำลังดาวน์โหลดเฉพาะคลิปนี้...",
     "YouTube Music with list= -> playlist warning"),
]


# ---------------------------------------------------------------------------
# Batch result summary logic (mirrors _batch_done)
# ---------------------------------------------------------------------------

def get_batch_summary(success: int, total: int, failed_count: int) -> str:
    """Simulate _batch_done() summary text."""
    if failed_count > 0:
        return f"เสร็จ! สำเร็จ {success}/{total} — ไม่สำเร็จ {failed_count} เพลง"
    return f"เสร็จ! ดาวน์โหลดสำเร็จ {success}/{total} เพลง"


def get_retry_button_text(failed_count: int) -> str:
    """Return retry button label for N failures."""
    return f"ลองใหม่ ({failed_count} เพลง)"


def get_checkbox_text(index: int, title: str, status: str, error: str = None) -> str:
    """Mirror _update_checkbox() formatting."""
    num = index + 1
    suffixes = {
        "downloading": "(กำลังโหลด...)",
        "success": "[สำเร็จ]",
        "failed": f"[ไม่สำเร็จ — {(error or '')[:60]}]",
    }
    suffix = suffixes.get(status, "")
    return f"{num}. {title}  {suffix}"


def get_checkbox_color(status: str) -> str:
    """Mirror _update_checkbox() color logic."""
    colors = {
        "downloading": "#dce4ee",  # default/neutral
        "success": "#2ecc71",      # green
        "failed": "#e74c3c",       # red
    }
    return colors.get(status, "")


# ---------------------------------------------------------------------------
# Custom schedule validation (mirrors _parse_custom_schedule)
# ---------------------------------------------------------------------------

def validate_custom_schedule(date_str: str, time_str: str):
    """Mirror _parse_custom_schedule() validation.

    Returns parsed datetime on success, raises ValueError on failure.
    """
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    ict = _tz(_td(hours=7))

    if not date_str or not time_str:
        raise ValueError("กรุณากรอกวันที่และเวลา")

    try:
        dt = _dt.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
    except ValueError:
        raise ValueError("รูปแบบไม่ถูกต้อง (DD/MM/YYYY HH:MM)")

    dt = dt.replace(tzinfo=ict)

    if dt <= _dt.now(ict):
        raise ValueError("เวลาต้องเป็นอนาคต")

    return dt


# ---------------------------------------------------------------------------
# Hook preview helpers (mirrors gui.py hook preview logic)
# ---------------------------------------------------------------------------

def get_hook_filename(song_title: str, hook_length: int, manual_start: float = None) -> str:
    """Mirror hook filename generation from _on_preview_hook()."""
    safe_title = song_title.replace(' ', '_')
    if manual_start is not None:
        return f"{safe_title}_hook_{hook_length}s_at{int(manual_start)}s.wav"
    return f"{safe_title}_hook_{hook_length}s.wav"


def validate_hook_start(start_str: str, song_length: float):
    """Mirror manual start validation from _on_preview_hook().

    Returns float on success, raises ValueError on failure.
    """
    if not start_str:
        raise ValueError("ค่าว่าง")
    start_sec = float(start_str)
    if start_sec < 0:
        raise ValueError("ค่าต้องมากกว่า 0")
    if start_sec >= song_length:
        raise ValueError(f"ตำแหน่งเกินความยาวเพลง ({song_length:.0f} วินาที)")
    return start_sec


def should_reuse_preview(preview_path: str, hook_length: int) -> bool:
    """Mirror preview reuse logic from _on_generate()."""
    if not preview_path:
        return False
    import os
    basename = os.path.basename(preview_path)
    return str(hook_length) in basename


HOOK_FILENAME_TESTS = [
    # (song_title, hook_length, manual_start, expected, label)
    ("My Song", 30, None,
     "My_Song_hook_30s.wav",
     "auto-detect -> standard filename"),
    ("My Song", 20, None,
     "My_Song_hook_20s.wav",
     "different length -> different filename"),
    ("My Song", 30, 45.0,
     "My_Song_hook_30s_at45s.wav",
     "manual start -> includes position"),
    ("My Song", 30, 0.0,
     "My_Song_hook_30s_at0s.wav",
     "manual start at 0 -> at0s"),
    ("เพลงไทย Test", 25, None,
     "เพลงไทย_Test_hook_25s.wav",
     "Thai title -> spaces replaced"),
    ("Song A", 30, 120.0,
     "Song_A_hook_30s_at120s.wav",
     "manual start 120s -> at120s"),
]

HOOK_START_TESTS = [
    # (start_str, song_length, should_pass, label)
    ("30", 180.0, True, "30s in 180s song -> OK"),
    ("0", 180.0, True, "0s start -> OK"),
    ("179", 180.0, True, "near end -> OK"),
    ("180", 180.0, False, "at song length -> error"),
    ("200", 180.0, False, "beyond song length -> error"),
    ("-5", 180.0, False, "negative start -> error"),
    ("abc", 180.0, False, "non-numeric -> error"),
    ("", 180.0, False, "empty string -> error"),
]

HOOK_REUSE_TESTS = [
    # (preview_path, hook_length, expected_reuse, label)
    ("outputs/My_Song_hook_30s.wav", 30, True, "matching 30s -> reuse"),
    ("outputs/My_Song_hook_30s.wav", 20, False, "length mismatch 30 vs 20 -> no reuse"),
    ("outputs/My_Song_hook_30s_at45s.wav", 30, True, "manual start with matching length -> reuse"),
    (None, 30, False, "no preview -> no reuse"),
    ("", 30, False, "empty path -> no reuse"),
    ("outputs/My_Song_hook_20s.wav", 20, True, "matching 20s -> reuse"),
]


BATCH_RESULT_TESTS = [
    # (success, total, failed_count, expected_text, label)
    (10, 10, 0,
     "เสร็จ! ดาวน์โหลดสำเร็จ 10/10 เพลง",
     "all success -> clean message"),

    (8, 10, 2,
     "เสร็จ! สำเร็จ 8/10 — ไม่สำเร็จ 2 เพลง",
     "partial failure -> breakdown"),

    (0, 5, 5,
     "เสร็จ! สำเร็จ 0/5 — ไม่สำเร็จ 5 เพลง",
     "all failed -> breakdown"),

    (1, 1, 0,
     "เสร็จ! ดาวน์โหลดสำเร็จ 1/1 เพลง",
     "single video success"),
]

CHECKBOX_TEXT_TESTS = [
    # (index, title, status, error, expected, label)
    (0, "Song A", "downloading", None,
     "1. Song A  (กำลังโหลด...)",
     "downloading state"),

    (2, "Song C", "success", None,
     "3. Song C  [สำเร็จ]",
     "success state"),

    (4, "Song E", "failed", "yt-dlp error",
     "5. Song E  [ไม่สำเร็จ — yt-dlp error]",
     "failed state with error"),

    (0, "Song F", "failed", "x" * 100,
     f"1. Song F  [ไม่สำเร็จ — {'x' * 60}]",
     "failed state with long error truncation"),
]

RETRY_BTN_TESTS = [
    (2, "ลองใหม่ (2 เพลง)", "2 failures"),
    (1, "ลองใหม่ (1 เพลง)", "1 failure"),
    (10, "ลองใหม่ (10 เพลง)", "10 failures"),
]

# Color coding tests: (status, expected_color, label)
COLOR_TESTS = [
    ("downloading", "#dce4ee", "downloading -> neutral color"),
    ("success", "#2ecc71", "success -> green"),
    ("failed", "#e74c3c", "failed -> red"),
]

# Custom schedule validation tests: (date, time, should_pass, label)
SCHEDULE_TESTS = [
    # Format validation
    ("", "19:00", False, "empty date -> error"),
    ("27/02/2026", "", False, "empty time -> error"),
    ("", "", False, "both empty -> error"),
    ("2026-02-27", "19:00", False, "wrong date format (YYYY-MM-DD) -> error"),
    ("27/02/2026", "7pm", False, "wrong time format (7pm) -> error"),
    ("32/02/2026", "19:00", False, "invalid day 32 -> error"),
    ("27/13/2026", "19:00", False, "invalid month 13 -> error"),
    ("27/02/2026", "25:00", False, "invalid hour 25 -> error"),
    # Past date (using a date that's definitely in the past)
    ("01/01/2020", "12:00", False, "past date -> error"),
    # Future date (using a date far in the future)
    ("01/01/2030", "19:00", True, "future date -> OK"),
    ("15/06/2028", "08:30", True, "another future date -> OK"),
]


# ---------------------------------------------------------------------------
# TikTok scheduling validation (mirrors validate_tiktok_schedule)
# ---------------------------------------------------------------------------

def validate_tiktok_schedule(publish_at_iso: str):
    """Mirror validate_tiktok_schedule() from tiktok_browser.py.

    Validates: >=20 min future, <=10 days, rounds to 5-min multiples.
    Returns adjusted datetime on success, raises ValueError on failure.
    """
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    dt = _dt.fromisoformat(publish_at_iso)
    if dt.tzinfo is None:
        ict = _tz(_td(hours=7))
        dt = dt.replace(tzinfo=ict)

    # Round minutes to nearest 5
    remainder = dt.minute % 5
    if remainder != 0:
        dt += _td(minutes=5 - remainder)
        dt = dt.replace(second=0, microsecond=0)

    now_utc = _dt.now(_tz.utc)
    min_time = now_utc + _td(minutes=20)
    max_time = now_utc + _td(days=10)

    if dt < min_time:
        raise ValueError("TikTok ตั้งเวลาได้อย่างน้อย 20 นาทีในอนาคต")
    if dt > max_time:
        raise ValueError("TikTok ตั้งเวลาได้ไม่เกิน 10 วัน")

    return dt


def _make_future_iso(hours: int = 0, days: int = 0, minutes: int = 0) -> str:
    """Helper: generate ISO datetime string at a future offset from now."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    ict = _tz(_td(hours=7))
    dt = _dt.now(ict) + _td(hours=hours, days=days, minutes=minutes)
    # Round to nearest 5 min for clean comparison
    remainder = dt.minute % 5
    if remainder != 0:
        dt += _td(minutes=5 - remainder)
    dt = dt.replace(second=0, microsecond=0)
    return dt.isoformat()


# TikTok schedule tests: (iso_string_or_factory, should_pass, label)
TIKTOK_SCHEDULE_TESTS = [
    # Too soon (5 min from now)
    (lambda: _make_future_iso(minutes=5), False, "5 min from now -> too soon"),
    # Just barely enough (25 min from now)
    (lambda: _make_future_iso(minutes=25), True, "25 min from now -> OK"),
    # 1 hour from now
    (lambda: _make_future_iso(hours=1), True, "1 hour from now -> OK"),
    # 1 day from now
    (lambda: _make_future_iso(days=1), True, "1 day from now -> OK"),
    # 5 days from now
    (lambda: _make_future_iso(days=5), True, "5 days from now -> OK"),
    # 10 days from now (borderline)
    (lambda: _make_future_iso(days=9, hours=23), True, "9 days 23h from now -> OK"),
    # 11 days from now (too far)
    (lambda: _make_future_iso(days=11), False, "11 days from now -> too far"),
    # Past datetime
    ("2020-01-01T12:00:00+07:00", False, "past date -> error"),
]

# TikTok minute rounding tests: (minute_in, expected_rounded)
TIKTOK_MINUTE_ROUND_TESTS = [
    (0, 0, "0 stays 0"),
    (5, 5, "5 stays 5"),
    (10, 10, "10 stays 10"),
    (1, 5, "1 rounds to 5"),
    (3, 5, "3 rounds to 5"),
    (7, 10, "7 rounds to 10"),
    (11, 15, "11 rounds to 15"),
    (14, 15, "14 rounds to 15"),
    (58, 0, "58 rounds to 0 (next hour)"),
]


def run_tests():
    passed = 0
    failed = 0

    print("=== Batch Scanner Feedback Tests ===\n")
    for url, expected_text, label in SCAN_TESTS:
        actual = get_scan_feedback(url)
        ok = actual == expected_text
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        URL:      {url}")
            print(f"        Expected: {expected_text}")
            print(f"        Got:      {actual}")

    print(f"\n=== Single-Download Feedback Tests ===\n")
    for url, expected_text, label in DOWNLOAD_TESTS:
        actual = get_download_feedback(url)
        ok = actual == expected_text
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        URL:      {url}")
            print(f"        Expected: {expected_text}")
            print(f"        Got:      {actual}")

    print(f"\n=== Batch Result Summary Tests ===\n")
    for success_n, total_n, failed_n, expected_text, label in BATCH_RESULT_TESTS:
        actual = get_batch_summary(success_n, total_n, failed_n)
        ok = actual == expected_text
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Expected: {expected_text}")
            print(f"        Got:      {actual}")

    print(f"\n=== Checkbox Status Text Tests ===\n")
    for idx, title, status, error, expected_text, label in CHECKBOX_TEXT_TESTS:
        actual = get_checkbox_text(idx, title, status, error)
        ok = actual == expected_text
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Expected: {expected_text}")
            print(f"        Got:      {actual}")

    print(f"\n=== Retry Button Text Tests ===\n")
    for count, expected_text, label in RETRY_BTN_TESTS:
        actual = get_retry_button_text(count)
        ok = actual == expected_text
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Expected: {expected_text}")
            print(f"        Got:      {actual}")

    print(f"\n=== Checkbox Color Tests ===\n")
    for status, expected_color, label in COLOR_TESTS:
        actual = get_checkbox_color(status)
        ok = actual == expected_color
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Expected: {expected_color}")
            print(f"        Got:      {actual}")

    print(f"\n=== Hook Preview Filename Tests ===\n")
    for song, length, manual_start, expected, label in HOOK_FILENAME_TESTS:
        actual = get_hook_filename(song, length, manual_start)
        ok = actual == expected
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Expected: {expected}")
            print(f"        Got:      {actual}")

    print(f"\n=== Hook Start Validation Tests ===\n")
    for start_str, song_length, should_pass, label in HOOK_START_TESTS:
        try:
            validate_hook_start(start_str, song_length)
            ok = should_pass
            if ok:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected error but got success")
        except ValueError as e:
            ok = not should_pass
            if ok:
                passed += 1
                print(f"  PASS  {label} (error: {e})")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected success but got: {e}")

    print(f"\n=== Hook Preview Reuse Tests ===\n")
    for preview_path, hook_length, expected_reuse, label in HOOK_REUSE_TESTS:
        actual = should_reuse_preview(preview_path, hook_length)
        ok = actual == expected_reuse
        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Expected: {expected_reuse}")
            print(f"        Got:      {actual}")

    print(f"\n=== Custom Schedule Validation Tests ===\n")
    for date_str, time_str, should_pass, label in SCHEDULE_TESTS:
        try:
            validate_custom_schedule(date_str, time_str)
            ok = should_pass
            if ok:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected error but got success")
        except ValueError as e:
            ok = not should_pass
            if ok:
                passed += 1
                print(f"  PASS  {label} (error: {e})")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected success but got: {e}")

    print(f"\n=== TikTok Schedule Validation Tests ===\n")
    for iso_or_fn, should_pass, label in TIKTOK_SCHEDULE_TESTS:
        iso_str = iso_or_fn() if callable(iso_or_fn) else iso_or_fn
        try:
            validate_tiktok_schedule(iso_str)
            ok = should_pass
            if ok:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected error but got success")
        except ValueError as e:
            ok = not should_pass
            if ok:
                passed += 1
                print(f"  PASS  {label} (error: {e})")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected success but got: {e}")

    print(f"\n=== TikTok Minute Rounding Tests ===\n")
    for minute_in, expected_out, label in TIKTOK_MINUTE_ROUND_TESTS:
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        ict = _tz(_td(hours=7))
        # Build a datetime 2 days in future with the given minute
        base = _dt.now(ict) + _td(days=2)
        base = base.replace(minute=minute_in, second=0, microsecond=0)
        try:
            result = validate_tiktok_schedule(base.isoformat())
            actual_minute = result.minute
            ok = actual_minute == expected_out
            if ok:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected minute={expected_out}, got minute={actual_minute}")
        except ValueError as e:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        Unexpected error: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
