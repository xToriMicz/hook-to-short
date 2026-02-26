"""
TikTok Browser Uploader — Selenium + Edge + Cookie Persistence
อัปโหลดวิดีโอไปยัง TikTok ผ่าน browser automation (ไม่ต้องใช้ API)

Flow:
1. ครั้งแรก: เปิด Edge ให้ user login → บันทึก cookie เป็น JSON
2. ครั้งต่อไป: โหลด cookie → อัปโหลดอัตโนมัติ

Language: Force English via browser preferences + URL param
เพื่อให้ selector ทำงานถูกต้องเสมอ ไม่ว่า user ตั้งภาษาอะไร
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable
from pathlib import Path

from . import UploadResult, UploadStatus, UploadRequest

logger = logging.getLogger(__name__)

COOKIE_FILE = "tiktok_cookies.json"
TIKTOK_DOMAIN = "https://www.tiktok.com"
TIKTOK_UPLOAD_URL = f"{TIKTOK_DOMAIN}/upload?lang=en"
TIKTOK_LOGIN_URL = f"{TIKTOK_DOMAIN}/login?lang=en"

# Max wait times (seconds)
LOGIN_TIMEOUT = 300  # 5 min for manual login
UPLOAD_TIMEOUT = 120  # 2 min for video processing
PUBLISH_TIMEOUT = 60  # 1 min for publish confirmation

# Emoji mapping for caption decoration
_EMOJI_KEYWORDS = {
    "bloom": "\ud83c\udf38", "flower": "\ud83c\udf3a", "rose": "\ud83c\udf39",
    "love": "\u2764\ufe0f", "heart": "\ud83d\udc96", "kiss": "\ud83d\udc8b",
    "sad": "\ud83d\ude22", "cry": "\ud83d\ude2d", "broken": "\ud83d\udc94",
    "night": "\ud83c\udf19", "moon": "\ud83c\udf1a", "star": "\u2b50",
    "sun": "\u2600\ufe0f", "morning": "\ud83c\udf05", "sunset": "\ud83c\udf07",
    "rain": "\ud83c\udf27\ufe0f", "cloud": "\u2601\ufe0f",
    "fire": "\ud83d\udd25", "hot": "\ud83d\udd25", "lit": "\ud83d\udd25",
    "music": "\ud83c\udfb5", "song": "\ud83c\udfb6", "sing": "\ud83c\udfa4",
    "dance": "\ud83d\udc83", "party": "\ud83c\udf89",
    "chill": "\ud83d\ude0e", "lofi": "\ud83c\udfa7", "vibe": "\ud83c\udf00",
    "dream": "\ud83d\udcad", "sleep": "\ud83d\ude34",
    "happy": "\ud83d\ude04", "smile": "\ud83d\ude0a", "joy": "\ud83d\ude01",
    "cool": "\ud83d\ude0e", "wow": "\ud83e\udd29",
    "\u0e23\u0e31\u0e01": "\u2764\ufe0f", "\u0e43\u0e08": "\ud83d\udc96",
    "\u0e04\u0e37\u0e19": "\ud83c\udf19", "\u0e01\u0e25\u0e32\u0e07\u0e04\u0e37\u0e19": "\ud83c\udf19",
    "\u0e40\u0e1e\u0e25\u0e07": "\ud83c\udfb5", "\u0e14\u0e2d\u0e01": "\ud83c\udf38",
    "\u0e1d\u0e19": "\ud83c\udf27\ufe0f", "\u0e1d\u0e31\u0e19": "\ud83d\udcad",
    "\u0e22\u0e34\u0e49\u0e21": "\ud83d\ude0a", "\u0e40\u0e28\u0e23\u0e49\u0e32": "\ud83d\ude22",
    "\u0e2a\u0e1a\u0e15\u0e32": "\ud83d\udc40",
}


def _pick_emoji(title: str) -> str:
    """Pick 1-2 relevant emojis based on title keywords."""
    title_lower = title.lower()
    found = []
    for keyword, emoji in _EMOJI_KEYWORDS.items():
        if keyword in title_lower and emoji not in found:
            found.append(emoji)
            if len(found) >= 2:
                break
    return "".join(found) if found else "\ud83c\udfb5"  # default: music note


def _create_edge_driver(headless: bool = False):
    """Create Edge WebDriver with English language forced.

    Uses Selenium's built-in Selenium Manager to auto-find msedgedriver.
    No need for webdriver-manager package.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options as EdgeOptions
    except ImportError:
        raise ImportError(
            "ต้องติดตั้ง: pip install selenium"
        )

    options = EdgeOptions()

    # Force English language — critical for reliable selectors
    options.add_argument("--lang=en-US")
    options.add_experimental_option("prefs", {
        "intl.accept_languages": "en-US,en",
    })

    # General options
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    if headless:
        options.add_argument("--headless=new")

    # Selenium Manager auto-finds msedgedriver (built into selenium>=4.10)
    driver = webdriver.Edge(options=options)
    driver.set_window_size(1280, 900)

    return driver


def _save_cookies(driver, cookie_path: str):
    """Save all cookies from browser to JSON file."""
    cookies = driver.get_cookies()
    with open(cookie_path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    logger.info(f"TikTok: บันทึก cookie แล้ว ({len(cookies)} cookies)")


def _load_cookies(driver, cookie_path: str) -> bool:
    """Load cookies from JSON file into browser. Returns True if loaded."""
    if not os.path.exists(cookie_path):
        return False

    try:
        with open(cookie_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except (json.JSONDecodeError, IOError):
        logger.warning("TikTok: cookie file corrupted")
        return False

    # Navigate to TikTok domain first (required before setting cookies)
    driver.get(TIKTOK_DOMAIN + "?lang=en")
    time.sleep(2)

    now = time.time()
    loaded = 0
    for cookie in cookies:
        # Skip expired cookies
        if "expiry" in cookie and cookie["expiry"] < now:
            continue
        # Some cookie fields cause issues — clean up
        for key in ["sameSite", "httpOnly", "storeId"]:
            cookie.pop(key, None)
        try:
            driver.add_cookie(cookie)
            loaded += 1
        except Exception:
            pass  # Skip problematic cookies

    logger.info(f"TikTok: โหลด {loaded}/{len(cookies)} cookies")
    return loaded > 0


def _fill_caption(driver, element, text: str):
    """Fill TikTok's DraftEditor caption field reliably using clipboard paste.

    DraftEditor is a React component that doesn't respond well to
    document.execCommand('insertText'). Clipboard paste (Ctrl+V) works
    because DraftEditor handles paste events natively.
    """
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains

    # Step 1: Click to focus
    driver.execute_script("arguments[0].click();", element)
    time.sleep(1)

    # Step 2: Select all existing text (Ctrl+A) and delete
    actions = ActionChains(driver)
    actions.click(element).perform()
    time.sleep(0.5)
    actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
    time.sleep(0.5)
    actions.send_keys(Keys.BACKSPACE).perform()
    time.sleep(1)

    # Step 3: Double check it's cleared
    remaining = driver.execute_script(
        "return arguments[0].textContent.trim().length;", element)
    if remaining > 0:
        # More aggressive clear
        actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        time.sleep(0.3)
        actions.send_keys(Keys.DELETE).perform()
        time.sleep(0.5)

    # Step 4: Paste caption via clipboard (Ctrl+V)
    # Use JS to set clipboard, then Ctrl+V to paste into DraftEditor
    driver.execute_script("""
        // Write text to clipboard via Clipboard API
        navigator.clipboard.writeText(arguments[0]).catch(function() {});
    """, text)
    time.sleep(0.5)

    # Focus element and paste
    actions = ActionChains(driver)
    actions.click(element).perform()
    time.sleep(0.3)
    actions.key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
    time.sleep(1)

    # Step 5: Verify — if clipboard paste didn't work, fall back to send_keys
    actual_len = driver.execute_script(
        "return arguments[0].textContent.trim().length;", element)
    if actual_len < 5:
        logger.warning("TikTok: clipboard paste ไม่ทำงาน — ลอง send_keys")
        actions.click(element).perform()
        time.sleep(0.3)
        element.send_keys(text)
        time.sleep(1)


def _dismiss_overlays(driver):
    """Dismiss Joyride tutorial overlays, modals, and cookie banners.

    TikTok shows a react-joyride tutorial overlay that blocks clicks.
    This removes them via JS so real elements become clickable.
    """
    try:
        driver.execute_script("""
            // Remove Joyride overlay (tutorial walkthrough)
            document.querySelectorAll('.react-joyride__overlay, .react-joyride').forEach(
                el => el.remove()
            );
            // Click any "Skip" or "Got it" or close buttons in modals
            var buttons = document.querySelectorAll(
                'button[data-joyride="close"], ' +
                'button[aria-label="Close"], ' +
                'button[aria-label="close"], ' +
                'div[role="dialog"] button'
            );
            buttons.forEach(btn => {
                var text = (btn.textContent || '').toLowerCase().trim();
                if (['skip', 'got it', 'close', 'x', 'dismiss', 'not now'].includes(text)
                    || btn.getAttribute('aria-label') === 'Close'
                    || btn.getAttribute('aria-label') === 'close') {
                    btn.click();
                }
            });
            // Remove any fixed/absolute overlays with high z-index that block interaction
            document.querySelectorAll('[style*="z-index"]').forEach(el => {
                var style = window.getComputedStyle(el);
                var zIndex = parseInt(style.zIndex) || 0;
                var position = style.position;
                if (zIndex > 1000 && (position === 'fixed' || position === 'absolute')
                    && el.classList.contains('react-joyride__overlay')) {
                    el.remove();
                }
            });
        """)
    except Exception:
        pass  # Best effort — don't fail if overlay dismissal fails


def _wait_for_video_ready(driver, timeout: int = 120):
    """Wait for TikTok to finish processing the uploaded video file.

    Polls for indicators that video processing is complete:
    - Caption editor becomes editable
    - Upload progress bar disappears or reaches 100%
    - Post button appears (even if disabled)

    Falls back to a minimum fixed wait if none of the signals are detected.
    """
    from selenium.webdriver.common.by import By

    start = time.time()
    min_wait = 5  # Always wait at least this long
    poll_interval = 2

    time.sleep(min_wait)

    while time.time() - start < timeout:
        try:
            # Check if a progress/processing indicator is still visible
            processing_indicators = driver.find_elements(By.CSS_SELECTOR, (
                '[class*="progress"], [class*="uploading"], '
                '[class*="processing"], [class*="loading"]'
            ))
            still_processing = False
            for el in processing_indicators:
                text = (el.text or "").lower()
                if any(w in text for w in ["uploading", "processing", "loading"]):
                    still_processing = True
                    break
                # Check for progress bar that's not at 100%
                width = el.value_of_css_property("width")
                if width and "%" in str(width):
                    still_processing = True
                    break

            if not still_processing:
                # Also check for the post button as a readiness signal
                post_btns = driver.find_elements(
                    By.CSS_SELECTOR, 'button[data-e2e="post_video_button"]')
                if post_btns:
                    logger.info("TikTok: วิดีโอประมวลผลเสร็จแล้ว")
                    return

            # Check if caption editor is available (another readiness signal)
            editors = driver.find_elements(
                By.CSS_SELECTOR, 'div[contenteditable="true"]')
            if editors and len(editors) > 0:
                logger.info("TikTok: caption editor พร้อมแล้ว")
                return

        except Exception:
            pass

        time.sleep(poll_interval)

    logger.info("TikTok: timeout รอวิดีโอ — ดำเนินการต่อ")


def _wait_for_post_ready(driver, timeout: int = 120):
    """Wait until the Post button is enabled (not disabled/greyed out).

    TikTok disables the Post button while video is still processing.
    This waits until it becomes clickable.
    """
    from selenium.webdriver.common.by import By

    start = time.time()
    poll_interval = 3
    time.sleep(3)  # Initial settle

    while time.time() - start < timeout:
        try:
            btn = _find_post_button(driver, timeout=5)
            if btn:
                # Check if button is enabled
                is_disabled = btn.get_attribute("disabled")
                aria_disabled = btn.get_attribute("aria-disabled")
                classes = btn.get_attribute("class") or ""
                if (not is_disabled and aria_disabled != "true"
                        and "disabled" not in classes):
                    logger.info("TikTok: ปุ่ม Post พร้อมกดแล้ว")
                    return
                logger.debug("TikTok: ปุ่ม Post ยัง disabled อยู่ — รอต่อ...")
        except Exception:
            pass
        time.sleep(poll_interval)

    logger.warning("TikTok: timeout รอปุ่ม Post — ลองกดเลย")


def _find_post_button(driver, timeout: int = 30):
    """Find the Post/Publish button using multiple selector strategies.

    Returns the button element or None.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    # Strategy 1: data-e2e attribute (most stable)
    css_selectors = [
        'button[data-e2e="post_video_button"]',
        'button[data-e2e="post-button"]',
        'button[data-e2e="publish_button"]',
    ]
    for selector in css_selectors:
        try:
            btn = WebDriverWait(driver, min(timeout, 10)).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            if btn:
                return btn
        except Exception:
            continue

    # Strategy 2: XPath text matching (English UI)
    xpath_selectors = [
        '//button[contains(text(), "Post")]',
        '//button[contains(text(), "post")]',
        '//button[contains(text(), "Publish")]',
        '//button[contains(text(), "publish")]',
        '//div[contains(@class, "btn-post")]//button',
        '//div[contains(@class, "post")]//button',
    ]
    for xpath in xpath_selectors:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            if btn:
                return btn
        except Exception:
            continue

    # Strategy 3: JS-based search for button with "Post" text
    try:
        btn = driver.execute_script("""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].textContent || '').trim().toLowerCase();
                if (text === 'post' || text === 'publish') {
                    return buttons[i];
                }
            }
            return null;
        """)
        if btn:
            return btn
    except Exception:
        pass

    return None


def _find_schedule_button(driver, timeout: int = 30):
    """Find the Schedule button (replaces Post when scheduling is enabled).

    Returns the button element or None.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    # Strategy 1: data-e2e attribute
    css_selectors = [
        'button[data-e2e="post_video_button"]',
        'button[data-e2e="schedule_button"]',
        'button[data-e2e="post-button"]',
    ]
    for selector in css_selectors:
        try:
            btn = WebDriverWait(driver, min(timeout, 10)).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            if btn:
                return btn
        except Exception:
            continue

    # Strategy 2: XPath text matching
    xpath_selectors = [
        '//button[contains(text(), "Schedule")]',
        '//button[contains(text(), "schedule")]',
        '//button[.//div[text()="Schedule"]]',
        '//button[contains(text(), "Post")]',
    ]
    for xpath in xpath_selectors:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            if btn:
                return btn
        except Exception:
            continue

    # Strategy 3: JS-based search
    try:
        btn = driver.execute_script("""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].textContent || '').trim().toLowerCase();
                if (text === 'schedule' || text === 'post') {
                    return buttons[i];
                }
            }
            return null;
        """)
        if btn:
            return btn
    except Exception:
        pass

    return None


def _wait_for_upload_success(driver, timeout: int = 60) -> bool:
    """Wait for TikTok to confirm the upload was successful.

    Checks multiple signals: success text, URL change, "upload another" button.
    Returns True if success was detected, False otherwise.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.by import By

    success_xpaths = [
        '//*[contains(text(), "uploaded")]',
        '//*[contains(text(), "Your video is being uploaded")]',
        '//*[contains(text(), "being processed")]',
        '//*[contains(text(), "successfully")]',
        '//*[contains(text(), "Manage your posts")]',
        '//*[contains(text(), "Upload another")]',
        '//*[contains(text(), "upload another")]',
        '//*[contains(text(), "Your video has been")]',
        '//*[contains(text(), "video is live")]',
        '//*[contains(text(), "scheduled")]',
        '//*[contains(text(), "will be posted")]',
        '//*[contains(text(), "video is scheduled")]',
    ]

    start = time.time()
    poll_interval = 3

    while time.time() - start < timeout:
        # Check text-based signals
        for xpath in success_xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                if elements:
                    logger.info("TikTok: ตรวจพบข้อความสำเร็จ")
                    return True
            except Exception:
                continue

        # Check URL change (redirect away from upload page = likely success)
        try:
            current_url = driver.current_url
            if "/upload" not in current_url and "tiktok.com" in current_url:
                logger.info("TikTok: redirect จากหน้า upload — น่าจะสำเร็จ")
                return True
        except Exception:
            pass

        # Check via JS for any success-related elements
        try:
            found = driver.execute_script("""
                var body = document.body.innerText.toLowerCase();
                var signals = ['uploaded', 'manage your posts', 'upload another',
                               'successfully', 'video is live', 'being processed',
                               'scheduled', 'will be posted', 'video is scheduled'];
                for (var i = 0; i < signals.length; i++) {
                    if (body.indexOf(signals[i]) !== -1) return true;
                }
                return false;
            """)
            if found:
                logger.info("TikTok: JS ตรวจพบสัญญาณสำเร็จ")
                return True
        except Exception:
            pass

        time.sleep(poll_interval)

    logger.warning("TikTok: ไม่พบสัญญาณสำเร็จชัดเจน — ถือว่าสำเร็จ (best-effort)")
    return False


# ---------------------------------------------------------------------------
# TikTok Scheduling — browser automation for the schedule toggle + date/time
# ---------------------------------------------------------------------------
# Constraints: >=20 min in future, <=10 days, minutes in multiples of 5.
# Reference: TikTok creator-center upload page (English UI).

TIKTOK_MIN_SCHEDULE_MINUTES = 20
TIKTOK_MAX_SCHEDULE_DAYS = 10
TIKTOK_MINUTE_MULTIPLE = 5

# XPath selectors for TikTok's scheduling UI
_SCHED_SELECTORS = {
    # Schedule toggle — TikTok uses a radio/switch button
    "switch": [
        '//*[@id="tux-1"]',
        '//div[contains(@class, "switch") and contains(@class, "schedule")]',
        '//label[contains(text(), "Schedule")]/ancestor::div[contains(@class, "switch")]',
        '//span[contains(text(), "Schedule video")]/ancestor::label',
    ],
    "date_picker": "//div[contains(@class, 'date-picker-input')]",
    "calendar": "//div[contains(@class, 'calendar-wrapper')]",
    "calendar_month": "//span[contains(@class, 'month-title')]",
    "calendar_valid_days": (
        "//div[contains(@class, 'days-wrapper')]"
        "//span[contains(@class, 'day') and contains(@class, 'valid')]"
    ),
    "calendar_arrows": "//span[contains(@class, 'arrow')]",
    "time_picker": "//div[contains(@class, 'time-picker-input')]",
    "time_picker_container": "//div[contains(@class, 'time-picker-container')]",
    "timepicker_hours": "//span[contains(@class, 'tiktok-timepicker-left')]",
    "timepicker_minutes": "//span[contains(@class, 'tiktok-timepicker-right')]",
    "time_picker_text": "//div[contains(@class, 'time-picker-input')]/*[1]",
}


def validate_tiktok_schedule(publish_at_iso: str) -> datetime:
    """Validate and adjust a publish_at ISO string for TikTok's constraints.

    Returns a timezone-aware datetime rounded to the nearest 5-minute multiple.
    Raises ValueError if the time is out of TikTok's allowed range.
    """
    dt = datetime.fromisoformat(publish_at_iso)
    if dt.tzinfo is None:
        # Assume ICT (UTC+7) if no timezone
        ict = timezone(timedelta(hours=7))
        dt = dt.replace(tzinfo=ict)

    # Round minutes up to nearest 5-minute multiple
    remainder = dt.minute % TIKTOK_MINUTE_MULTIPLE
    if remainder != 0:
        dt += timedelta(minutes=TIKTOK_MINUTE_MULTIPLE - remainder)
        dt = dt.replace(second=0, microsecond=0)

    now_utc = datetime.now(timezone.utc)
    min_time = now_utc + timedelta(minutes=TIKTOK_MIN_SCHEDULE_MINUTES)
    max_time = now_utc + timedelta(days=TIKTOK_MAX_SCHEDULE_DAYS)

    if dt < min_time:
        raise ValueError(
            f"TikTok ตั้งเวลาได้อย่างน้อย {TIKTOK_MIN_SCHEDULE_MINUTES} นาทีในอนาคต"
        )
    if dt > max_time:
        raise ValueError(
            f"TikTok ตั้งเวลาได้ไม่เกิน {TIKTOK_MAX_SCHEDULE_DAYS} วัน"
        )

    return dt


def _set_schedule_video(driver, schedule_dt: datetime):
    """Enable TikTok scheduling and set date/time via browser automation.

    Args:
        driver: Selenium WebDriver
        schedule_dt: timezone-aware datetime (already validated & rounded)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Get browser timezone and convert schedule to it
    browser_tz_name = driver.execute_script(
        "return Intl.DateTimeFormat().resolvedOptions().timeZone")
    try:
        import zoneinfo
        browser_tz = zoneinfo.ZoneInfo(browser_tz_name)
    except (ImportError, KeyError):
        # Fallback: use UTC offset from browser
        offset_min = driver.execute_script(
            "return -new Date().getTimezoneOffset()")
        browser_tz = timezone(timedelta(minutes=offset_min))

    local_dt = schedule_dt.astimezone(browser_tz)
    target_month = local_dt.month
    target_day = local_dt.day
    target_hour = local_dt.hour
    target_minute = local_dt.minute

    logger.info(f"TikTok: ตั้งเวลา {local_dt.strftime('%Y-%m-%d %H:%M')} "
                f"(tz: {browser_tz_name})")

    # Step 1: Click schedule toggle/switch
    _click_schedule_switch(driver)
    time.sleep(1)

    # Step 2: Set date
    _pick_schedule_date(driver, target_month, target_day)
    time.sleep(0.5)

    # Step 3: Set time
    _pick_schedule_time(driver, target_hour, target_minute)
    time.sleep(0.5)

    logger.info("TikTok: ตั้งเวลาสำเร็จ")


def _click_schedule_switch(driver):
    """Click the schedule toggle switch using multiple selector strategies."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    selectors = _SCHED_SELECTORS["switch"]
    for xpath in selectors:
        try:
            el = WebDriverWait(driver, 5).until(
                lambda d, x=xpath: d.find_element(By.XPATH, x)
            )
            if el and el.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView(true);", el)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", el)
                logger.debug(f"TikTok: schedule switch clicked via: {xpath}")
                return
        except Exception:
            continue

    # Fallback: JS search for any element with "Schedule" text
    clicked = driver.execute_script("""
        // Look for radio/toggle with "Schedule" label text
        var labels = document.querySelectorAll('label, span, div');
        for (var i = 0; i < labels.length; i++) {
            var text = (labels[i].textContent || '').trim().toLowerCase();
            if (text === 'schedule video' || text === 'schedule') {
                // Click the parent container or the element itself
                var target = labels[i].closest('label') || labels[i];
                target.click();
                return true;
            }
        }
        return false;
    """)
    if clicked:
        logger.debug("TikTok: schedule switch clicked via JS fallback")
        return

    raise Exception("TikTok: หาปุ่ม Schedule ไม่เจอ")


def _pick_schedule_date(driver, month: int, day: int):
    """Navigate TikTok's calendar and select the target date."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Click date picker to open calendar
    date_picker = WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.XPATH, _SCHED_SELECTORS["date_picker"])
    )
    driver.execute_script("arguments[0].click();", date_picker)
    time.sleep(1)

    # Wait for calendar to appear
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.XPATH, _SCHED_SELECTORS["calendar"]))
    )

    # Check current month and navigate if needed
    month_el = driver.find_element(By.XPATH, _SCHED_SELECTORS["calendar_month"])
    current_month_name = month_el.text.strip()
    try:
        current_month = datetime.strptime(current_month_name, "%B").month
    except ValueError:
        # Try abbreviated month name
        current_month = datetime.strptime(current_month_name[:3], "%b").month

    # Navigate months (forward or backward)
    max_nav = 12  # safety limit
    while current_month != month and max_nav > 0:
        arrows = driver.find_elements(By.XPATH, _SCHED_SELECTORS["calendar_arrows"])
        if not arrows or len(arrows) < 2:
            break
        if current_month < month:
            driver.execute_script("arguments[0].click();", arrows[-1])  # next
        else:
            driver.execute_script("arguments[0].click();", arrows[0])  # prev
        time.sleep(0.5)
        month_el = driver.find_element(By.XPATH, _SCHED_SELECTORS["calendar_month"])
        current_month_name = month_el.text.strip()
        try:
            current_month = datetime.strptime(current_month_name, "%B").month
        except ValueError:
            current_month = datetime.strptime(current_month_name[:3], "%b").month
        max_nav -= 1

    # Click the target day
    valid_days = driver.find_elements(
        By.XPATH, _SCHED_SELECTORS["calendar_valid_days"])

    clicked = False
    for day_el in valid_days:
        if day_el.text.strip() == str(day):
            driver.execute_script("arguments[0].click();", day_el)
            clicked = True
            break

    if not clicked:
        raise Exception(f"TikTok: หาวันที่ {day} ไม่เจอในปฏิทิน")

    logger.debug(f"TikTok: เลือกวันที่ {month}/{day}")


def _pick_schedule_time(driver, hour: int, minute: int):
    """Select hour and minute from TikTok's time picker."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Click time picker to open dropdown
    time_picker = WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.XPATH, _SCHED_SELECTORS["time_picker"])
    )
    driver.execute_script("arguments[0].click();", time_picker)
    time.sleep(1)

    # Wait for time picker container
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((
            By.XPATH, _SCHED_SELECTORS["time_picker_container"]))
    )

    # Select hour (0-23, directly indexable)
    hour_options = driver.find_elements(
        By.XPATH, _SCHED_SELECTORS["timepicker_hours"])
    if hour < len(hour_options):
        target_hour = hour_options[hour]
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", target_hour)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", target_hour)
    else:
        raise Exception(f"TikTok: หาชั่วโมง {hour} ไม่เจอ (มี {len(hour_options)} ตัวเลือก)")

    time.sleep(0.5)

    # Select minute (in multiples of 5, so index = minute / 5)
    minute_options = driver.find_elements(
        By.XPATH, _SCHED_SELECTORS["timepicker_minutes"])
    minute_idx = minute // TIKTOK_MINUTE_MULTIPLE
    if minute_idx < len(minute_options):
        target_minute = minute_options[minute_idx]
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", target_minute)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", target_minute)
    else:
        raise Exception(f"TikTok: หานาที {minute} ไม่เจอ (มี {len(minute_options)} ตัวเลือก)")

    # Close time picker by clicking it again
    driver.execute_script("arguments[0].click();", time_picker)
    time.sleep(0.5)

    logger.debug(f"TikTok: เลือกเวลา {hour:02d}:{minute:02d}")


class TikTokBrowserUploader:
    """Upload videos to TikTok via browser automation (Selenium + Edge)."""

    def __init__(self, cookie_path: str = COOKIE_FILE):
        self.cookie_path = cookie_path

    def is_configured(self) -> bool:
        """Cookie file exists = configured."""
        return os.path.exists(self.cookie_path)

    def login(self) -> bool:
        """Open browser for user to login manually, then save cookies.

        Returns True if login was successful (cookies saved).
        """
        driver = None
        try:
            logger.info("TikTok: เปิดเบราว์เซอร์เพื่อ login...")
            driver = _create_edge_driver(headless=False)
            driver.get(TIKTOK_LOGIN_URL)

            # Wait for user to login — detect by checking for logged-in state
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By

            logger.info("TikTok: กรุณา login ในเบราว์เซอร์ (รอ 5 นาที)...")

            # Wait until URL no longer contains /login OR a profile element appears
            def is_logged_in(drv):
                url = drv.current_url
                # User navigated away from login page = likely logged in
                if "/login" not in url and "tiktok.com" in url:
                    return True
                # Check for session cookie
                cookies = drv.get_cookies()
                session_cookies = [c for c in cookies
                                   if c["name"] in ("sessionid", "sid_tt", "sessionid_ss")]
                return len(session_cookies) > 0

            WebDriverWait(driver, LOGIN_TIMEOUT).until(is_logged_in)

            # Give a moment for all cookies to settle
            time.sleep(3)

            _save_cookies(driver, self.cookie_path)
            logger.info("TikTok: login สำเร็จ — cookie บันทึกแล้ว")
            return True

        except Exception as e:
            logger.error(f"TikTok: login ไม่สำเร็จ — {e}")
            return False

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def clear_cookies(self):
        """Delete saved cookie file for re-login."""
        if os.path.exists(self.cookie_path):
            os.remove(self.cookie_path)
            logger.info("TikTok: ลบ cookie แล้ว")

    def upload(self, request: UploadRequest,
               progress_callback: Optional[Callable[[float], None]] = None) -> UploadResult:
        """Upload video via tiktok.com/upload using browser automation."""
        if not self.is_configured():
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error="ยังไม่ได้ login TikTok — ไปที่ตั้งค่า > Login TikTok",
            )

        if not os.path.exists(request.video_path):
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error=f"ไม่พบไฟล์วิดีโอ: {request.video_path}",
            )

        video_path = str(Path(request.video_path).resolve())
        driver = None

        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys

            logger.info(f"TikTok: เริ่มอัปโหลด '{request.title}'...")
            driver = _create_edge_driver(headless=False)

            # Step 1: Load cookies
            if not _load_cookies(driver, self.cookie_path):
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error="โหลด cookie ไม่ได้ — ลอง login ใหม่",
                )

            # Step 2: Navigate to upload page
            driver.get(TIKTOK_UPLOAD_URL)
            # Wait for page to be interactive (not just loaded)
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)

            # Step 3: Check if still logged in (redirected to login = session expired)
            if "/login" in driver.current_url:
                self.clear_cookies()
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error="Session หมดอายุ — กรุณา login ใหม่ในตั้งค่า",
                )

            if progress_callback:
                progress_callback(0.1)

            # Dismiss any overlay/tutorial popups (Joyride, modals, etc.)
            _dismiss_overlays(driver)

            # Step 4: Find file input and upload video
            # TikTok upload page uses an <input type="file"> element
            try:
                file_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
                )
                file_input.send_keys(video_path)
                logger.info("TikTok: เลือกไฟล์แล้ว — กำลังประมวลผล...")
            except Exception as e:
                self._screenshot_on_error(driver, "select_file")
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error=f"หาช่องเลือกไฟล์ไม่เจอ: {str(e)[:100]}",
                )

            if progress_callback:
                progress_callback(0.3)

            # Step 5: Wait for video processing (TikTok needs time to process)
            logger.info("TikTok: รอประมวลผลวิดีโอ...")
            # Smart wait: poll for caption editor to become available (signals processing done)
            # Falls back to fixed wait if editor not found within timeout
            _wait_for_video_ready(driver, timeout=UPLOAD_TIMEOUT)

            # Dismiss overlays again (TikTok may show tutorial after file select)
            _dismiss_overlays(driver)
            time.sleep(1)

            if progress_callback:
                progress_callback(0.5)

            # Step 6: Fill caption (title + emoji + hashtags)
            caption = f"{request.title} {_pick_emoji(request.title)}"
            if request.description:
                caption = f"{caption}\n{request.description}"
            if request.tags:
                caption += "\n" + " ".join(f"#{t}" for t in request.tags)

            try:
                # TikTok's caption editor — DraftEditor or newer editor
                # Multiple selectors for resilience against UI changes
                caption_selectors = [
                    # DraftEditor (classic)
                    'div.DraftEditor-root div[contenteditable="true"]',
                    'div[contenteditable="true"][data-text="true"]',
                    'div[aria-autocomplete="list"][contenteditable="true"]',
                    # Newer TikTok editor variants
                    'div[data-e2e="caption-editor"] div[contenteditable="true"]',
                    'div[class*="caption"] div[contenteditable="true"]',
                    'div[class*="editor"] div[contenteditable="true"]',
                    # Broadest fallback
                    'div[contenteditable="true"]',
                ]

                caption_input = None
                for selector in caption_selectors:
                    try:
                        caption_input = WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        if caption_input:
                            logger.debug(f"TikTok: caption editor found with: {selector}")
                            break
                    except Exception:
                        continue

                if caption_input:
                    _fill_caption(driver, caption_input, caption[:2200])
                    time.sleep(1)
                    actual = driver.execute_script(
                        "return arguments[0].textContent.trim();", caption_input)
                    logger.info(f"TikTok: กรอก caption แล้ว ({len(actual)} chars)")
                else:
                    logger.warning("TikTok: หา caption input ไม่เจอ — ข้ามไป")

            except Exception as e:
                logger.warning(f"TikTok: กรอก caption ไม่ได้ — {e}")

            if progress_callback:
                progress_callback(0.6)

            # Step 6.5: Set schedule if publish_at is provided
            is_scheduled = False
            if request.publish_at:
                try:
                    schedule_dt = validate_tiktok_schedule(request.publish_at)
                    _set_schedule_video(driver, schedule_dt)
                    is_scheduled = True
                    logger.info(f"TikTok: ตั้งเวลาโพส {schedule_dt.strftime('%Y-%m-%d %H:%M')}")
                except ValueError as e:
                    logger.warning(f"TikTok: ตั้งเวลาไม่ได้ — {e} — โพสทันทีแทน")
                except Exception as e:
                    logger.warning(f"TikTok: ตั้งเวลาไม่สำเร็จ — {e} — โพสทันทีแทน")
                    self._screenshot_on_error(driver, "schedule")

            if progress_callback:
                progress_callback(0.7)

            # Step 7: Wait for upload/processing to finish before clicking post
            logger.info("TikTok: รอก่อนกด Post...")
            _wait_for_post_ready(driver, timeout=UPLOAD_TIMEOUT)

            # Dismiss overlays one more time before clicking Post
            _dismiss_overlays(driver)

            # Step 8: Click Post/Schedule button
            btn_label = "Schedule" if is_scheduled else "Post"
            try:
                if is_scheduled:
                    post_btn = _find_schedule_button(driver, timeout=30)
                else:
                    post_btn = _find_post_button(driver, timeout=30)

                if post_btn:
                    # Use JS click to bypass any overlay
                    driver.execute_script("arguments[0].scrollIntoView(true);", post_btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", post_btn)
                    logger.info(f"TikTok: กดปุ่ม {btn_label} แล้ว")
                else:
                    self._screenshot_on_error(driver, "post_button")
                    return UploadResult(
                        platform="TikTok",
                        status=UploadStatus.FAILED,
                        error=f"หาปุ่ม {btn_label} ไม่เจอ — ดู screenshot ใน outputs/",
                    )

            except Exception as e:
                self._screenshot_on_error(driver, "post_click")
                return UploadResult(
                    platform="TikTok",
                    status=UploadStatus.FAILED,
                    error=f"กดปุ่ม {btn_label} ไม่ได้: {str(e)[:100]}",
                )

            # Step 8.5: Handle "Continue to post?" confirmation dialog
            # TikTok shows this while still checking video for issues
            # (only for immediate posts — scheduled posts don't show this)
            if not is_scheduled:
                try:
                    post_now_btn = WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            '//button[contains(text(), "Post") and contains(text(), "now")]'
                        ))
                    )
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", post_now_btn)
                    logger.info("TikTok: กดปุ่ม 'Post now' (confirm dialog) แล้ว")
                except Exception:
                    # No confirmation dialog — that's fine
                    try:
                        confirm_btn = driver.find_element(
                            By.CSS_SELECTOR,
                            'div[role="dialog"] button[class*="primary"], '
                            'div[role="dialog"] button[class*="red"], '
                            'div[role="dialog"] button:last-child'
                        )
                        if confirm_btn and confirm_btn.is_displayed():
                            driver.execute_script("arguments[0].click();", confirm_btn)
                            logger.info("TikTok: กดปุ่ม confirm ใน dialog แล้ว")
                    except Exception:
                        pass

            if progress_callback:
                progress_callback(0.9)

            # Step 9: Wait for success confirmation
            success_found = _wait_for_upload_success(driver, timeout=PUBLISH_TIMEOUT)

            # Step 10: Save updated cookies
            _save_cookies(driver, self.cookie_path)

            if progress_callback:
                progress_callback(1.0)

            logger.info("TikTok: อัปโหลดสำเร็จ")
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.SUCCESS,
            )

        except ImportError:
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error="ต้องติดตั้ง: pip install selenium",
            )

        except Exception as e:
            if driver:
                self._screenshot_on_error(driver, "unexpected")
            logger.error(f"TikTok: อัปโหลดไม่สำเร็จ — {e}")
            return UploadResult(
                platform="TikTok",
                status=UploadStatus.FAILED,
                error=f"อัปโหลดไม่สำเร็จ: {str(e)[:150]}",
            )

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    @staticmethod
    def _screenshot_on_error(driver, name: str):
        """Save screenshot for debugging when something goes wrong."""
        try:
            os.makedirs("outputs", exist_ok=True)
            path = f"outputs/tiktok_error_{name}_{int(time.time())}.png"
            driver.save_screenshot(path)
            logger.info(f"TikTok: screenshot saved — {path}")
        except Exception:
            pass
