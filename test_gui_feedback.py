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

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
