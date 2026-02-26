"""Unit tests for _classify_url() — all URL pattern variations."""
import re
from urllib.parse import urlparse, parse_qs


def _classify_url(url: str):
    """Mirror of HookToShortApp._classify_url() for standalone testing."""
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


# ---- Test cases ----

TESTS = [
    # === Single videos ===
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ",
     "video", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
     "standard watch URL"),

    ("https://youtube.com/watch?v=dQw4w9WgXcQ",
     "video", "https://youtube.com/watch?v=dQw4w9WgXcQ",
     "watch URL without www"),

    # === youtu.be short URLs ===
    ("https://youtu.be/dQw4w9WgXcQ",
     "video", "https://youtu.be/dQw4w9WgXcQ",
     "youtu.be short URL"),

    ("https://youtu.be/dQw4w9WgXcQ?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "playlist", "https://youtu.be/dQw4w9WgXcQ?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "youtu.be with playlist"),

    # === Shorts ===
    ("https://www.youtube.com/shorts/abcDEF12345",
     "video", "https://www.youtube.com/shorts/abcDEF12345",
     "shorts URL"),

    ("https://youtube.com/shorts/abc_DEF-123",
     "video", "https://youtube.com/shorts/abc_DEF-123",
     "shorts with underscore/dash"),

    # === Live ===
    ("https://www.youtube.com/live/abcDEF12345",
     "video", "https://www.youtube.com/live/abcDEF12345",
     "live URL"),

    # === Playlists ===
    ("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "playlist", "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
     "standard playlist"),

    ("https://www.youtube.com/watch?v=abc123&list=OLAK5uy_abc123",
     "playlist", "https://www.youtube.com/watch?v=abc123&list=OLAK5uy_abc123",
     "watch URL with playlist param"),

    # === music.youtube.com ===
    ("https://music.youtube.com/playlist?list=OLAK5uy_abc123",
     "playlist", "https://music.youtube.com/playlist?list=OLAK5uy_abc123",
     "YouTube Music playlist"),

    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ",
     "video", "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
     "YouTube Music single video"),

    ("https://music.youtube.com/watch?v=abc&list=RDCLAK5uy_abc",
     "playlist", "https://music.youtube.com/watch?v=abc&list=RDCLAK5uy_abc",
     "YouTube Music watch with playlist (radio/mix)"),

    # === Channel with @ handle ===
    ("https://www.youtube.com/@LosgaBb",
     "channel", "https://www.youtube.com/@LosgaBb/videos",
     "bare @channel -> appends /videos"),

    ("https://www.youtube.com/@LosgaBb/videos",
     "channel", "https://www.youtube.com/@LosgaBb/videos",
     "@channel already has /videos"),

    ("https://www.youtube.com/@LosgaBb/releases",
     "releases", "https://www.youtube.com/@LosgaBb/releases",
     "@channel releases tab"),

    # === Channel with /channel/UC... (no @) ===
    ("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
     "channel", "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw/videos",
     "channel ID (no @) -> appends /videos"),

    ("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw/videos",
     "channel", "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw/videos",
     "channel ID already has /videos"),

    # === /c/ custom URL ===
    ("https://www.youtube.com/c/SomeChannel",
     "channel", "https://www.youtube.com/c/SomeChannel/videos",
     "/c/ custom URL -> appends /videos"),

    ("https://www.youtube.com/c/SomeChannel/videos",
     "channel", "https://www.youtube.com/c/SomeChannel/videos",
     "/c/ already has /videos"),

    # === Trailing slash edge cases ===
    ("https://www.youtube.com/@LosgaBb/",
     "channel", "https://www.youtube.com/@LosgaBb/videos",
     "bare @channel with trailing slash"),
]


def run_tests():
    passed = 0
    failed = 0

    for url, expected_type, expected_url, label in TESTS:
        result_type, result_url = _classify_url(url)
        ok = result_type == expected_type and result_url == expected_url

        if ok:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}")
            print(f"        URL:      {url}")
            print(f"        Expected: ({expected_type}, {expected_url})")
            print(f"        Got:      ({result_type}, {result_url})")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
