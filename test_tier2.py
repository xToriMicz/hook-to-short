"""
Tier 2 feature tests — template persistence, library search/sort, batch generation logic.

Tests pure logic extracted from gui.py without requiring a display or tkinter.
"""
import json
import os
import tempfile
import shutil
from datetime import datetime


# ---------------------------------------------------------------------------
# Template persistence helpers (mirror gui.py load_settings / save_settings)
# ---------------------------------------------------------------------------

def load_settings(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def save_template(name: str, tpl: dict, settings_path: str):
    """Mirror _on_save_template() logic."""
    s = load_settings(settings_path)
    if "upload_templates" not in s:
        s["upload_templates"] = {}
    s["upload_templates"][name] = tpl
    save_settings(s, settings_path)


def load_template(name: str, settings_path: str) -> dict | None:
    """Mirror _on_load_template() logic."""
    if name == "(ไม่ใช้)":
        return None
    s = load_settings(settings_path)
    return s.get("upload_templates", {}).get(name)


def delete_template(name: str, settings_path: str) -> bool:
    """Mirror _on_delete_template() logic."""
    if name == "(ไม่ใช้)":
        return False
    s = load_settings(settings_path)
    templates = s.get("upload_templates", {})
    if name in templates:
        del templates[name]
        save_settings(s, settings_path)
        return True
    return False


def get_template_names(settings_path: str) -> list:
    """Mirror _refresh_template_list() logic."""
    s = load_settings(settings_path)
    templates = s.get("upload_templates", {})
    return ["(ไม่ใช้)"] + sorted(templates.keys())


# ---------------------------------------------------------------------------
# Library search/sort helpers (mirror _refresh_library() logic)
# ---------------------------------------------------------------------------

def filter_tracks(tracks: list, query: str) -> list:
    """Mirror library search filter."""
    query = query.strip().lower()
    if not query:
        return tracks
    return [t for t in tracks
            if query in t.get("title", "").lower()
            or query in t.get("artist", "").lower()]


def sort_tracks(tracks: list, sort_mode: str) -> list:
    """Mirror library sort. Returns a new sorted list."""
    result = list(tracks)
    if sort_mode == "เก่าสุด":
        result.sort(key=lambda t: t.get("created_at", ""))
    elif sort_mode == "ใหม่สุด":
        result.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    elif sort_mode == "ชื่อ A-Z":
        result.sort(key=lambda t: t.get("title", "").lower())
    elif sort_mode == "ชื่อ Z-A":
        result.sort(key=lambda t: t.get("title", "").lower(), reverse=True)
    elif sort_mode == "ขนาดมาก-น้อย":
        result.sort(key=lambda t: t.get("file_size_mb", 0), reverse=True)
    return result


def get_lib_count_text(total: int, shown: int, has_query: bool) -> str:
    """Mirror library count label text."""
    if has_query:
        return f"เพลง: {shown}/{total} เพลง"
    return f"เพลง: {total} เพลง"


# ---------------------------------------------------------------------------
# Batch generation helpers
# ---------------------------------------------------------------------------

def get_batch_display(title: str, artist: str, max_len: int = 60) -> str:
    """Mirror batch generation song list display text."""
    display = f"{title}  —  {artist}"
    if len(display) > max_len:
        display = display[:max_len - 3] + "..."
    return display


def get_batch_progress_text(idx: int, total: int, song_label: str) -> str:
    """Mirror batch generation progress label."""
    return f"กำลังสร้าง {idx + 1}/{total}: {song_label}"


def get_batch_done_text(success: int, total: int) -> str:
    """Mirror batch generation done text."""
    return f"เสร็จ! สร้างสำเร็จ {success}/{total} วิดีโอ"


def get_batch_settings_summary(style: str, platform: str, hook_len: int, font: str) -> str:
    """Mirror batch settings summary line."""
    return f"ตั้งค่า: {style} | {platform} | ฮุก {hook_len} วิ. | {font}"


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_TRACKS = [
    {"id": 1, "title": "ก่อนฤดูฝน", "artist": "LUSS", "file_size_mb": 5.2,
     "created_at": "2026-02-20T10:00:00"},
    {"id": 2, "title": "Beautiful Day", "artist": "U2", "file_size_mb": 8.1,
     "created_at": "2026-02-21T15:30:00"},
    {"id": 3, "title": "ลมหนาว", "artist": "BodySlam", "file_size_mb": 3.7,
     "created_at": "2026-02-19T08:00:00"},
    {"id": 4, "title": "Blinding Lights", "artist": "The Weeknd", "file_size_mb": 6.5,
     "created_at": "2026-02-22T20:00:00"},
    {"id": 5, "title": "เธอยัง", "artist": "LUSS", "file_size_mb": 4.3,
     "created_at": "2026-02-18T12:00:00"},
]

SAMPLE_TEMPLATE = {
    "description": "เพลงไทยฮิต #shorts",
    "tags": "Shorts, เพลง, เพลงไทย",
    "promo_link": "https://example.com",
    "publish_mode": "public",
    "youtube": True,
    "tiktok": True,
    "facebook": False,
}


# ---------------------------------------------------------------------------
# Template Persistence Tests
# ---------------------------------------------------------------------------

TPL_TESTS = [
    # (action, args, expected, label)
]


def run_template_tests(settings_path: str):
    passed = 0
    failed = 0

    # 1. Save template
    save_template("เพลงไทย", SAMPLE_TEMPLATE, settings_path)
    tpl = load_template("เพลงไทย", settings_path)
    if tpl == SAMPLE_TEMPLATE:
        passed += 1
        print("  PASS  save + load template")
    else:
        failed += 1
        print(f"  FAIL  save + load template\n        Got: {tpl}")

    # 2. Template list
    names = get_template_names(settings_path)
    if names == ["(ไม่ใช้)", "เพลงไทย"]:
        passed += 1
        print("  PASS  template list has 1 template")
    else:
        failed += 1
        print(f"  FAIL  template list\n        Got: {names}")

    # 3. Save second template
    save_template("English", {"description": "English music", "tags": "music", "promo_link": "",
                               "publish_mode": "private", "youtube": True, "tiktok": False, "facebook": False},
                  settings_path)
    names = get_template_names(settings_path)
    if names == ["(ไม่ใช้)", "English", "เพลงไทย"]:
        passed += 1
        print("  PASS  sorted template list with 2 templates")
    else:
        failed += 1
        print(f"  FAIL  sorted template list\n        Got: {names}")

    # 4. Overwrite template
    updated = dict(SAMPLE_TEMPLATE, description="Updated description")
    save_template("เพลงไทย", updated, settings_path)
    tpl = load_template("เพลงไทย", settings_path)
    if tpl["description"] == "Updated description":
        passed += 1
        print("  PASS  overwrite existing template")
    else:
        failed += 1
        print(f"  FAIL  overwrite\n        Got: {tpl}")

    # 5. Load nonexistent
    tpl = load_template("NoSuchTemplate", settings_path)
    if tpl is None:
        passed += 1
        print("  PASS  load nonexistent -> None")
    else:
        failed += 1
        print(f"  FAIL  load nonexistent\n        Got: {tpl}")

    # 6. Load (ไม่ใช้) sentinel
    tpl = load_template("(ไม่ใช้)", settings_path)
    if tpl is None:
        passed += 1
        print("  PASS  load '(ไม่ใช้)' -> None")
    else:
        failed += 1
        print(f"  FAIL  load sentinel\n        Got: {tpl}")

    # 7. Delete template
    ok = delete_template("English", settings_path)
    names = get_template_names(settings_path)
    if ok and names == ["(ไม่ใช้)", "เพลงไทย"]:
        passed += 1
        print("  PASS  delete template")
    else:
        failed += 1
        print(f"  FAIL  delete template\n        ok={ok}, names={names}")

    # 8. Delete nonexistent
    ok = delete_template("Ghost", settings_path)
    if not ok:
        passed += 1
        print("  PASS  delete nonexistent -> False")
    else:
        failed += 1
        print("  FAIL  delete nonexistent should return False")

    # 9. Delete sentinel
    ok = delete_template("(ไม่ใช้)", settings_path)
    if not ok:
        passed += 1
        print("  PASS  delete '(ไม่ใช้)' -> False")
    else:
        failed += 1
        print("  FAIL  delete sentinel should return False")

    # 10. Template with empty fields
    empty_tpl = {"description": "", "tags": "", "promo_link": "",
                 "publish_mode": "public", "youtube": False, "tiktok": False, "facebook": False}
    save_template("Empty", empty_tpl, settings_path)
    tpl = load_template("Empty", settings_path)
    if tpl == empty_tpl:
        passed += 1
        print("  PASS  template with all empty fields")
    else:
        failed += 1
        print(f"  FAIL  empty template\n        Got: {tpl}")

    # 11. Template with special characters
    special_tpl = dict(SAMPLE_TEMPLATE, description='Tags: #music & "quotes" \'apos\'')
    save_template("Special!@#$", special_tpl, settings_path)
    tpl = load_template("Special!@#$", settings_path)
    if tpl and tpl["description"] == special_tpl["description"]:
        passed += 1
        print("  PASS  template with special characters")
    else:
        failed += 1
        print(f"  FAIL  special chars\n        Got: {tpl}")

    # 12. Persistence across reload (re-read from disk)
    names_reloaded = get_template_names(settings_path)
    if "เพลงไทย" in names_reloaded and "Empty" in names_reloaded and "Special!@#$" in names_reloaded:
        passed += 1
        print("  PASS  templates persist on disk")
    else:
        failed += 1
        print(f"  FAIL  persistence\n        Got: {names_reloaded}")

    # 13. Other settings not clobbered
    s = load_settings(settings_path)
    if s.get("hook_length") == 60:
        passed += 1
        print("  PASS  other settings preserved")
    else:
        failed += 1
        print(f"  FAIL  other settings clobbered\n        Got: {s}")

    return passed, failed


# ---------------------------------------------------------------------------
# Library Search Tests
# ---------------------------------------------------------------------------

SEARCH_TESTS = [
    # (query, expected_ids, label)
    ("", [1, 2, 3, 4, 5], "empty query -> all tracks"),
    ("luss", [1, 5], "search by artist (case-insensitive)"),
    ("LUSS", [1, 5], "search by artist (uppercase)"),
    ("ลม", [3], "search Thai title partial match"),
    ("beautiful", [2], "search English title"),
    ("xyz_nomatch", [], "no matches -> empty"),
    ("  luss  ", [1, 5], "query with whitespace padding"),
    ("u2", [2], "short artist name"),
    ("blind", [4], "partial title match"),
    ("เธอ", [5], "Thai partial title"),
    ("body", [3], "artist partial match (BodySlam)"),
]


SORT_TESTS = [
    # (sort_mode, expected_id_order, label)
    ("ใหม่สุด", [4, 2, 1, 3, 5], "newest first"),
    ("เก่าสุด", [5, 3, 1, 2, 4], "oldest first"),
    ("ชื่อ A-Z", [2, 4, 1, 3, 5], "name A-Z (English before Thai)"),
    ("ชื่อ Z-A", [5, 3, 1, 4, 2], "name Z-A"),
    ("ขนาดมาก-น้อย", [2, 4, 1, 5, 3], "size descending"),
]


COUNT_TEXT_TESTS = [
    # (total, shown, has_query, expected, label)
    (10, 10, False, "เพลง: 10 เพลง", "no query -> total only"),
    (10, 3, True, "เพลง: 3/10 เพลง", "with query -> shown/total"),
    (0, 0, False, "เพลง: 0 เพลง", "empty library"),
    (5, 0, True, "เพลง: 0/5 เพลง", "query with no matches"),
]


# ---------------------------------------------------------------------------
# Batch Generation Tests
# ---------------------------------------------------------------------------

BATCH_DISPLAY_TESTS = [
    # (title, artist, expected, label)
    ("My Song", "Artist", "My Song  —  Artist", "short display"),
    ("A" * 50, "B" * 20, ("A" * 50 + "  —  " + "B" * 20)[:57] + "...", "long display truncated"),
    ("", "ไม่ทราบ", "  —  ไม่ทราบ", "empty title"),
    ("Song", "", "Song  —  ", "empty artist"),
]

BATCH_PROGRESS_TESTS = [
    (0, 5, "Song A", "กำลังสร้าง 1/5: Song A", "first of 5"),
    (4, 5, "Song E", "กำลังสร้าง 5/5: Song E", "last of 5"),
    (0, 1, "Only", "กำลังสร้าง 1/1: Only", "single song"),
]

BATCH_DONE_TESTS = [
    (3, 3, "เสร็จ! สร้างสำเร็จ 3/3 วิดีโอ", "all success"),
    (2, 5, "เสร็จ! สร้างสำเร็จ 2/5 วิดีโอ", "partial"),
    (0, 3, "เสร็จ! สร้างสำเร็จ 0/3 วิดีโอ", "all failed"),
]

BATCH_SETTINGS_TESTS = [
    ("Korean", "TikTok", 30, "พู่กันโรแมนติก",
     "ตั้งค่า: Korean | TikTok | ฮุก 30 วิ. | พู่กันโรแมนติก", "standard"),
    ("Minimal", "YouTube Shorts", 60, "ตัวหนา",
     "ตั้งค่า: Minimal | YouTube Shorts | ฮุก 60 วิ. | ตัวหนา", "different settings"),
]


# ---------------------------------------------------------------------------
# File Import helpers (mirror gui.py _parse_drop_data / _import_files logic)
# ---------------------------------------------------------------------------

def parse_drop_data(data: str) -> list:
    """Parse tkinterdnd2 drop event data into a list of file paths."""
    paths = []
    i = 0
    while i < len(data):
        if data[i] == '{':
            end = data.index('}', i + 1)
            paths.append(data[i + 1:end])
            i = end + 2
        elif data[i] == ' ':
            i += 1
        else:
            end = data.find(' ', i)
            if end == -1:
                end = len(data)
            paths.append(data[i:end])
            i = end + 1
    return paths


def resolve_import_dest(basename: str, downloads_dir: str) -> str:
    """Resolve destination path, adding _2, _3 suffix for duplicates."""
    dest = os.path.join(downloads_dir, basename)
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(basename)
    counter = 2
    while os.path.exists(dest):
        dest = os.path.join(downloads_dir, f"{stem}_{counter}{ext}")
        counter += 1
    return dest


def filter_import_paths(paths: list, downloads_dir: str) -> tuple:
    """Filter file paths: only MP3, not already in downloads. Returns (mp3_paths, skipped)."""
    mp3 = []
    skipped = 0
    dl_norm = os.path.normpath(downloads_dir)
    for p in paths:
        p = p.strip()
        if not p:
            continue
        if not p.lower().endswith(".mp3"):
            skipped += 1
            continue
        if os.path.normpath(os.path.dirname(os.path.abspath(p))) == dl_norm:
            skipped += 1
            continue
        mp3.append(p)
    return mp3, skipped


PARSE_DROP_TESTS = [
    # (input, expected_paths, label)
    ("C:/song1.mp3 C:/song2.mp3",
     ["C:/song1.mp3", "C:/song2.mp3"],
     "simple space-separated paths"),
    ("{C:/My Music/song.mp3} C:/song2.mp3",
     ["C:/My Music/song.mp3", "C:/song2.mp3"],
     "braced path with spaces + simple path"),
    ("{C:/My Music/my song.mp3}",
     ["C:/My Music/my song.mp3"],
     "single braced path"),
    ("C:/a.mp3",
     ["C:/a.mp3"],
     "single path no braces"),
    ("",
     [],
     "empty string"),
    ("{C:/a b/c.mp3} {D:/x y/z.mp3}",
     ["C:/a b/c.mp3", "D:/x y/z.mp3"],
     "multiple braced paths"),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests():
    passed = 0
    failed = 0

    # Create temp dir for settings tests
    tmp_dir = tempfile.mkdtemp(prefix="hts_test_")
    settings_path = os.path.join(tmp_dir, "settings.json")
    # Seed with existing settings to test preservation
    save_settings({"hook_length": 60, "video_style": "Korean"}, settings_path)

    try:
        print("=== Template Persistence Tests ===\n")
        p, f = run_template_tests(settings_path)
        passed += p
        failed += f

        print(f"\n=== Library Search Filter Tests ===\n")
        for query, expected_ids, label in SEARCH_TESTS:
            result = filter_tracks(SAMPLE_TRACKS, query)
            actual_ids = [t["id"] for t in result]
            if actual_ids == expected_ids:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected IDs: {expected_ids}")
                print(f"        Got IDs:      {actual_ids}")

        print(f"\n=== Library Sort Tests ===\n")
        for sort_mode, expected_order, label in SORT_TESTS:
            result = sort_tracks(SAMPLE_TRACKS, sort_mode)
            actual_order = [t["id"] for t in result]
            if actual_order == expected_order:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected_order}")
                print(f"        Got:      {actual_order}")

        print(f"\n=== Library Count Text Tests ===\n")
        for total, shown, has_query, expected, label in COUNT_TEXT_TESTS:
            actual = get_lib_count_text(total, shown, has_query)
            if actual == expected:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected}")
                print(f"        Got:      {actual}")

        print(f"\n=== Batch Display Text Tests ===\n")
        for title, artist, expected, label in BATCH_DISPLAY_TESTS:
            actual = get_batch_display(title, artist)
            if actual == expected:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected}")
                print(f"        Got:      {actual}")

        print(f"\n=== Batch Progress Text Tests ===\n")
        for idx, total, song, expected, label in BATCH_PROGRESS_TESTS:
            actual = get_batch_progress_text(idx, total, song)
            if actual == expected:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected}")
                print(f"        Got:      {actual}")

        print(f"\n=== Batch Done Text Tests ===\n")
        for success, total, expected, label in BATCH_DONE_TESTS:
            actual = get_batch_done_text(success, total)
            if actual == expected:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected}")
                print(f"        Got:      {actual}")

        print(f"\n=== Batch Settings Summary Tests ===\n")
        for style, plat, hook, font, expected, label in BATCH_SETTINGS_TESTS:
            actual = get_batch_settings_summary(style, plat, hook, font)
            if actual == expected:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected}")
                print(f"        Got:      {actual}")

        # --- File Import Tests ---
        print(f"\n=== Drop Data Parse Tests ===\n")
        for data, expected, label in PARSE_DROP_TESTS:
            actual = parse_drop_data(data)
            if actual == expected:
                passed += 1
                print(f"  PASS  {label}")
            else:
                failed += 1
                print(f"  FAIL  {label}")
                print(f"        Expected: {expected}")
                print(f"        Got:      {actual}")

        print(f"\n=== Import Filter Tests ===\n")

        # Non-MP3 filtering
        mp3, skip = filter_import_paths(["a.mp3", "b.wav", "c.txt", "d.mp3"], tmp_dir)
        if [os.path.basename(p) for p in mp3] == ["a.mp3", "d.mp3"] and skip == 2:
            passed += 1
            print("  PASS  non-MP3 files filtered out")
        else:
            failed += 1
            print(f"  FAIL  non-MP3 filter — got mp3={mp3}, skip={skip}")

        # Already in downloads dir skipped
        in_dl = os.path.join(tmp_dir, "exists.mp3")
        with open(in_dl, "w") as f:
            f.write("fake")
        mp3, skip = filter_import_paths([in_dl], tmp_dir)
        if mp3 == [] and skip == 1:
            passed += 1
            print("  PASS  file already in downloads -> skipped")
        else:
            failed += 1
            print(f"  FAIL  already-in-downloads — got mp3={mp3}, skip={skip}")

        # Empty and whitespace paths
        mp3, skip = filter_import_paths(["", "  ", "  x.mp3  "], tmp_dir)
        # "  x.mp3  " after strip is "x.mp3" which ends with .mp3
        if len(mp3) == 1 and skip == 0:
            passed += 1
            print("  PASS  empty/whitespace paths handled")
        else:
            failed += 1
            print(f"  FAIL  empty paths — got mp3={mp3}, skip={skip}")

        print(f"\n=== Import Duplicate Filename Tests ===\n")

        dl_dir = os.path.join(tmp_dir, "downloads")
        os.makedirs(dl_dir, exist_ok=True)

        # No conflict
        dest = resolve_import_dest("new_song.mp3", dl_dir)
        if os.path.basename(dest) == "new_song.mp3":
            passed += 1
            print("  PASS  no conflict -> original name")
        else:
            failed += 1
            print(f"  FAIL  no conflict — got {dest}")

        # Create a file to trigger duplicate handling
        with open(os.path.join(dl_dir, "song.mp3"), "w") as f:
            f.write("fake")
        dest = resolve_import_dest("song.mp3", dl_dir)
        if os.path.basename(dest) == "song_2.mp3":
            passed += 1
            print("  PASS  first duplicate -> _2 suffix")
        else:
            failed += 1
            print(f"  FAIL  first dup — got {os.path.basename(dest)}")

        # Create _2 to get _3
        with open(os.path.join(dl_dir, "song_2.mp3"), "w") as f:
            f.write("fake")
        dest = resolve_import_dest("song.mp3", dl_dir)
        if os.path.basename(dest) == "song_3.mp3":
            passed += 1
            print("  PASS  second duplicate -> _3 suffix")
        else:
            failed += 1
            print(f"  FAIL  second dup — got {os.path.basename(dest)}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
