from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# Chrome Headless Settings for Mobile Emulation
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=412,915")

# Enable Mobile View Emulation (Pixel 5 / Mobile User-Agent)
mobile_emulation = {
    "deviceMetrics": { "width": 412, "height": 915, "pixelRatio": 3.0 },
    "userAgent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
}
chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)

# Driver Setup
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# --- Aapka baki ka Mobile Rank code iske niche normal chalega ---
import os
import re
import io
import math
import time
import base64
import unicodedata
import random
import logging
import shutil
import tempfile
import subprocess

from datetime import date, datetime

import pandas as pd

from urllib.parse import urlparse, parse_qs, unquote, quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)

try:
    from PIL import Image
except ImportError:
    Image = None


# ============================================================
# CONFIG
# ============================================================

BASE_PATH = r"D:\Python code\New Rank Automation"

INPUT_FILE = os.path.join(BASE_PATH, "keywords.txt")

OUTPUT_FILE_XLSX = os.path.join(BASE_PATH, "google_rank_mobile.xlsx")
OUTPUT_FILE_CSV = os.path.join(BASE_PATH, "google_rank_mobile_live.csv")

# Keep separate from the desktop profile
CHROME_PROFILE = r"C:\RankBotMobileProfile"

TARGET_DOMAIN = "gempundit.com"

MAX_ORGANIC_RESULTS = 10

GOOGLE_HOME = "https://www.google.co.in/"

RESULT_WAIT = 20
PAGE_LOAD_TIMEOUT = 30

MIN_SEARCH_DELAY = 5
MAX_SEARCH_DELAY = 9

BLOCK_RETRY_DELAY = 30

# In run_both.py (one shared terminal) ENTER cannot be pressed for one script, so the script
# keeps checking by itself for this many seconds whether the verification was solved in Chrome.
BLOCK_AUTO_WAIT_SECONDS = 600


# True  = delete ALL previous data (Excel, CSV, Screenshots) on EVERY run -> fresh start, new files.
# False = delete only data from yesterday or older (today's data is kept).
AUTO_DELETE_OLD_DATA = True
CLEAN_EVERY_RUN = True

# Only relevant when CLEAN_EVERY_RUN = False: today's leftover data is resumed.
RESUME_SAME_DAY = False

# Files modified by another script within this many seconds are not deleted
# (so two scripts running side by side do not delete each other's data)
RECENT_PROTECT_SECONDS = 90

# Screenshots: <BASE_PATH>\Screenshots\<DD-MM-YYYY>\mobile\
TAKE_SCREENSHOTS = True

# Show a #rank badge on counted results (to match the screenshot with the Excel)
ANNOTATE_SCREENSHOTS = True

# Show an orange 'SKIP: reason' badge on skipped titles (see what was skipped and why)
ANNOTATE_SKIPPED = True

# No domain is skipped (social media such as YouTube/Facebook/Instagram is counted too)
SKIP_DOMAINS = set()

# If there are 0 results, the HTML + a screenshot are saved
DEBUG_ON_EMPTY = True

# On mobile Google a title is an <h3> or a <div role="heading">
# <a><h3> / <a><div role=heading> -> result titles
TITLE_CSS = "a h3, a div[role='heading']"

# True = links inside Google's own sections (SKIP_SECTIONS: AI Overview, People also ask, Images,
#        Videos, Deals, Popular products ...) are NEVER counted.
#        (A title that has its own domain line is always organic; this filter never removes it.)
USE_SECTION_FILTER = True

# Even without a domain line, treat an <h3> title with a direct external link as organic
ACCEPT_H3_WITHOUT_DOMAIN_LINE = True

# No link/name/domain inside these sections is counted
SKIP_SECTIONS = [
    "ai overview",
    "people also ask",
    "people also search for",
    "popular products",
    "images",
    "deals",
    "in shops nearby",
    "videos",
    "short videos",
    "sponsored products",
    "places",
    "top stories",
    "things to know",
    "related searches",
    "from sources across the web",
    "shopping",
]

# How many titles in the last search had no readable domain
LAST_UNREADABLE = 0

logging.getLogger("selenium").setLevel(logging.CRITICAL)


# ============================================================
# SCREENSHOT HELPERS (full page, no cuts / no overlap)
# Required: pip install pillow
# ============================================================

# ============================================================
# CONFIG
# ============================================================

# Maximum page height (CSS px). Taller pages are cut here (protects against infinite scroll)
MAX_PAGE_HEIGHT = 20000

# Height captured per chunk (CSS px). Kept small so that
# the screenshot is never cut by Chrome's texture limit (~16384 px).
CHUNK_HEIGHT = 2500


# ============================================================
# FILE / FOLDER
# ============================================================

def safe_filename(text, max_len=60):

    """
    Windows-safe filename. Keeps Hindi/Unicode letters and combining marks (ु, ्, ा ...),
    and replaces every other symbol with '_'.
    """

    cleaned = []

    for ch in str(text):

        if ch.isalnum() or unicodedata.category(ch).startswith("M") or ch in "-_":
            cleaned.append(ch)
        else:
            cleaned.append("_")

    name = re.sub(r"_+", "_", "".join(cleaned)).strip("_")

    return (name[:max_len] or "keyword")


def get_screenshot_folder(base_path, device):

    """
    <base_path>/Screenshots/<DD-MM-YYYY>/<device>/
    """

    day = datetime.now().strftime("%d-%m-%Y")

    folder = os.path.join(base_path, "Screenshots", day, device)

    os.makedirs(folder, exist_ok=True)

    return folder


def unique_path(folder, name):

    path = os.path.join(folder, name + ".png")

    if os.path.exists(path):

        stamp = datetime.now().strftime("%H%M%S")

        path = os.path.join(folder, f"{name}_{stamp}.png")

    return path


# ============================================================
# PAGE LOAD
# ============================================================

def _page_height(driver):

    try:
        return int(driver.execute_script(
            "return Math.max("
            "document.body ? document.body.scrollHeight : 0,"
            "document.documentElement.scrollHeight,"
            "document.body ? document.body.offsetHeight : 0,"
            "document.documentElement.offsetHeight);"
        ) or 0)
    except Exception:
        return 0


def force_render_all(driver):

    """
    Some pages do not render off-screen results (content-visibility: auto),
    which makes their text/size come back empty. Force-render everything.
    """

    try:
        driver.execute_script("""
            if (!document.getElementById('rb-force-render')) {
                const s = document.createElement('style');
                s.id = 'rb-force-render';
                s.textContent = '* { content-visibility: visible !important; }';
                (document.head || document.documentElement).appendChild(s);
            }
        """)
    except Exception:
        pass


def wait_page_fully_loaded(driver, log=print):

    """
    1) readyState == complete
    2) scroll to the bottom (to trigger lazy-loaded content/images)
    3) wait until all visible images are loaded
    4) go back to the top and wait until the page height is stable
    """

    # ---- 1) readyState --------------------------------------
    start = time.time()

    while time.time() - start < 15:

        try:
            if driver.execute_script("return document.readyState") == "complete":
                break
        except Exception:
            pass

        time.sleep(0.5)

    force_render_all(driver)

    # ---- 2) scroll through ----------------------------------
    try:
        viewport = int(driver.execute_script("return window.innerHeight") or 800)

        pos = 0

        for _ in range(60):

            limit = min(_page_height(driver), MAX_PAGE_HEIGHT)

            if pos >= limit - viewport:
                break

            pos += int(viewport * 0.8)

            driver.execute_script("window.scrollTo(0, arguments[0]);", pos)

            time.sleep(0.45)

        driver.execute_script(
            "window.scrollTo(0, Math.min(document.documentElement.scrollHeight, arguments[0]));",
            MAX_PAGE_HEIGHT
        )

        time.sleep(1)

    except Exception as e:
        log(f"⚠️ Scroll error: {e}")

    # ---- 3) images ------------------------------------------
    end = time.time() + 10

    while time.time() < end:

        try:
            done = driver.execute_script("""
                return Array.from(document.images)
                    .filter(i => {
                        const r = i.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    })
                    .every(i => i.complete);
            """)

            if done:
                break

        except Exception:
            break

        time.sleep(0.5)

    # ---- 4) top + stable height -----------------------------
    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass

    time.sleep(0.8)

    previous = -1

    for _ in range(8):

        height = _page_height(driver)

        if height == previous:
            break

        previous = height

        time.sleep(0.8)

    log(f"📄 Page fully loaded (height ≈ {previous}px)")


# ============================================================
# ANNOTATE (Excel <-> screenshot match)
# ============================================================

def annotate_results(driver, results, target_domain, log=print, skipped=None):

    """
    A '#<rank> <domain>' badge + outline on the title of every counted organic result.
    The target domain (gempundit) is green, the rest are red.
    results = [{"domain":..., "element": <WebElement>}, ...]
    """

    target_domain = (target_domain or "").lower()

    for rank, item in enumerate(results, start=1):

        element = item.get("element")

        if element is None:
            continue

        domain = (item.get("domain") or "").lower()

        is_target = bool(
            target_domain
            and (domain == target_domain or domain.endswith("." + target_domain))
        )

        try:
            driver.execute_script("""
                const el = arguments[0];
                const rank = arguments[1];
                const isTarget = arguments[2];
                const domain = arguments[3];

                const color = isTarget ? '#0a8f3c' : '#d93025';

                const badge = document.createElement('span');

                badge.textContent = '#' + rank + '  ' + domain;
                badge.setAttribute('data-rb-badge', '1');

                badge.style.cssText =
                    'display:inline-block;background:' + color + ';color:#fff;' +
                    'font:bold 13px Arial,sans-serif;padding:2px 8px;' +
                    'margin:0 8px 2px 0;border-radius:4px;vertical-align:middle;' +
                    'line-height:18px;';

                el.prepend(badge);

                el.style.outline = '3px solid ' + color;
                el.style.outlineOffset = '2px';
            """, element, rank, is_target, domain)

        except Exception:
            # the element went stale -> skip the annotation (the screenshot is still taken)
            continue

    # Skipped titles: AD = purple badge, everything else orange (with the reason)
    for element, reason in (skipped or []):

        is_ad = str(reason).upper().startswith("AD")

        text = "AD (not counted)" if is_ad else "SKIP: " + str(reason)

        background = "#7b1fa2" if is_ad else "#f29900"

        foreground = "#ffffff" if is_ad else "#000000"

        try:
            driver.execute_script("""
                const el = arguments[0];
                const text = arguments[1];
                const bg = arguments[2];
                const fg = arguments[3];

                const badge = document.createElement('span');

                badge.textContent = text;
                badge.setAttribute('data-rb-badge', '1');

                badge.style.cssText =
                    'display:inline-block;background:' + bg + ';color:' + fg + ';' +
                    'font:bold 11px Arial,sans-serif;padding:1px 6px;' +
                    'margin:0 6px 2px 0;border-radius:4px;vertical-align:middle;' +
                    'line-height:16px;';

                el.prepend(badge);

                el.style.outline = '2px dotted ' + bg;
                el.style.outlineOffset = '2px';
            """, element, text, background, foreground)

        except Exception:
            continue


# ============================================================
# FULL PAGE SCREENSHOT
# ============================================================

def _hide_fixed(driver, keep_top):

    """
    Hide position: fixed / sticky elements so that they do not
    repeat in every chunk (avoids overlap / ghost headers).
    keep_top=True : keep only the header at the top of the page visible (in the first chunk).
    """

    driver.execute_script("""
        const keepTop = arguments[0];

        document.querySelectorAll('*').forEach(el => {

            const pos = getComputedStyle(el).position;

            if (pos === 'fixed' || pos === 'sticky') {

                const r = el.getBoundingClientRect();

                if (keepTop && r.top < 150 && r.top > -50) {
                    return;
                }

                if (!el.hasAttribute('data-rb-vis')) {
                    el.setAttribute('data-rb-vis', el.style.visibility || '__none__');
                }

                el.style.setProperty('visibility', 'hidden', 'important');
            }
        });
    """, bool(keep_top))


def _restore_fixed(driver):

    try:
        driver.execute_script("""
            document.querySelectorAll('[data-rb-vis]').forEach(el => {

                const v = el.getAttribute('data-rb-vis');

                el.style.removeProperty('visibility');

                if (v !== '__none__') {
                    el.style.visibility = v;
                }

                el.removeAttribute('data-rb-vis');
            });
        """)
    except Exception:
        pass


def take_full_page_screenshot(driver, filepath, log=print):

    """
    Full-page screenshot (top to bottom). Captured in chunks through Chrome CDP
    and stitched with Pillow -> no part is cut or overlapped.
    Return: True / False
    """

    try:
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass

    time.sleep(0.4)

    metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})

    content = metrics.get("cssContentSize") or metrics.get("contentSize")
    viewport = metrics.get("cssLayoutViewport") or metrics.get("layoutViewport")

    width = int(viewport["clientWidth"])

    full_height = int(math.ceil(content["height"]))

    height = min(full_height, MAX_PAGE_HEIGHT)

    if height <= 0 or width <= 0:
        log("⚠️ Could not read the page size, skipping the screenshot.")
        return False

    if full_height > MAX_PAGE_HEIGHT:
        log(f"⚠️ Page is very tall ({full_height}px). Capturing up to {MAX_PAGE_HEIGHT}px.")

    parts = []

    y = 0

    first = True

    try:
        while y < height:

            h = min(CHUNK_HEIGHT, height - y)

            _hide_fixed(driver, keep_top=first)

            data = driver.execute_cdp_cmd(
                "Page.captureScreenshot",
                {
                    "format": "png",
                    "fromSurface": True,
                    "captureBeyondViewport": True,
                    "clip": {
                        "x": 0,
                        "y": y,
                        "width": width,
                        "height": h,
                        "scale": 1
                    }
                }
            )

            parts.append(base64.b64decode(data["data"]))

            y += h

            first = False

    finally:
        _restore_fixed(driver)

    if not parts:
        return False

    # ---- save -------------------------------------------------
    if Image is None:

        if len(parts) == 1:

            with open(filepath, "wb") as f:
                f.write(parts[0])

            return True

        log("⚠️ Pillow is not installed (pip install pillow). Saving the chunks separately.")

        base, ext = os.path.splitext(filepath)

        for number, blob in enumerate(parts, start=1):

            with open(f"{base}_part{number:02d}{ext}", "wb") as f:
                f.write(blob)

        return True

    images = [Image.open(io.BytesIO(blob)).convert("RGB") for blob in parts]

    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)

    canvas = Image.new("RGB", (total_width, total_height), "white")

    offset = 0

    for img in images:

        canvas.paste(img, (0, offset))

        offset += img.height

    canvas.save(filepath, "PNG")

    log(f"📸 Screenshot saved: {filepath} ({total_width}x{total_height}px, {len(parts)} parts)")

    return True


# ============================================================
# ONE-CALL WRAPPER
# ============================================================

def capture_keyword_screenshot(
    driver,
    folder,
    index,
    keyword,
    organic_results=None,
    target_domain="",
    status="OK",
    annotate=True,
    log=print
):

    """
    Annotate (optional) + full-page screenshot.
    File: <folder>/<index>_<keyword>[_STATUS].png
    Returns: the full path of the saved file, or "" on failure.
    """

    try:
        if annotate:

            skipped = []

            if globals().get("ANNOTATE_SKIPPED", False):
                skipped = list(globals().get("LAST_SKIPPED", []))

            annotate_results(
                driver, organic_results or [], target_domain, log, skipped
            )

        name = f"{index:03d}_{safe_filename(keyword)}"

        if status and status != "OK":
            name += f"_{status}"

        path = unique_path(folder, name)

        if take_full_page_screenshot(driver, path, log):
            return path

    except Exception as e:

        log(f"⚠️ Screenshot error: {e}")

    return ""


# ============================================================
# GOOGLE DOMAINS
# ============================================================

GOOGLE_DOMAINS = {
    "google.com",
    "google.co.in",
    "google.co.uk",
    "google.ca",
    "google.com.au",
    "google.de",
    "google.fr",
    "google.co.nz",
    "google.co.jp",
    "googleusercontent.com",
    "gstatic.com",
    "googleadservices.com",
    "doubleclick.net",
    "googleweblight.com",
    "googleapis.com",
}

DOMAIN_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE
)


# ============================================================
# DOMAIN HELPERS
# ============================================================

def normalize_domain(domain):

    if not domain:
        return ""

    domain = str(domain).strip().lower().rstrip(".")

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def get_full_domain(url):

    if not url:
        return ""

    try:
        url = str(url).strip()

        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url

        domain = urlparse(url).netloc.lower().strip()

        if "@" in domain:
            domain = domain.split("@")[-1]

        domain = domain.split(":")[0]

        return normalize_domain(domain)

    except Exception:
        return ""


def is_valid_domain_format(domain):

    if not domain:
        return False

    domain = normalize_domain(domain)

    if "." not in domain:
        return False

    if any(c.isspace() for c in domain):
        return False

    bad_chars = ["₹", "$", "€", "£", "%", ",", "/", "\\",
                 ":", "?", "#", "(", ")", "[", "]"]

    if any(c in domain for c in bad_chars):
        return False

    if not DOMAIN_PATTERN.fullmatch(domain):
        return False

    return domain.rsplit(".", 1)[-1].isalpha()


def _matches(domain, base):

    return domain == base or domain.endswith("." + base)


def is_google_domain(domain):

    if not domain:
        return True

    domain = normalize_domain(domain)

    return any(_matches(domain, g) for g in GOOGLE_DOMAINS)


def is_skipped_domain(domain):

    return any(_matches(domain, s) for s in SKIP_DOMAINS)


def is_valid_result(url):

    if not url:
        return False

    try:
        if urlparse(url).scheme.lower() not in ("http", "https"):
            return False

        domain = get_full_domain(url)

        return bool(
            domain
            and is_valid_domain_format(domain)
            and not is_google_domain(domain)
        )

    except Exception:
        return False


def normalize_direct_url(url):

    if not url:
        return ""

    try:
        url = unquote(str(url).strip()).strip("\"'<>")

        if not re.match(r"^https?://", url, re.IGNORECASE):
            return ""

        if is_valid_result(url):
            return url

    except Exception:
        pass

    return ""


def extract_url_from_google_href(href):

    if not href:
        return ""

    try:
        href = str(href).strip()

        direct = normalize_direct_url(href)

        if direct:
            return direct

        params = parse_qs(urlparse(href).query)

        for key in ["url", "q", "u", "target", "dest", "destination", "uddg"]:

            for value in params.get(key, []):

                direct = normalize_direct_url(unquote(value))

                if direct:
                    return direct

        decoded = unquote(href)

        for candidate in re.findall(r'https?://[^"\s<>]+', decoded, re.IGNORECASE):

            direct = normalize_direct_url(candidate.rstrip(".,);:'\""))

            if direct:
                return direct

    except Exception:
        pass

    return ""


# ============================================================
# ELEMENT HELPERS
# ============================================================

def is_visible(driver, element):

    try:
        return bool(driver.execute_script("""
            const el = arguments[0];
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            if (rect.width <= 0 || rect.height <= 0) return false;
            if (style.display === 'none' ||
                style.visibility === 'hidden' ||
                style.opacity === '0') return false;
            return true;
        """, element))

    except Exception:
        return False


def get_anchor_href(anchor):

    for attr in ["href", "data-href", "data-url", "data-link"]:

        try:
            value = (anchor.get_attribute(attr) or "").strip()

            if value:
                return value

        except Exception:
            continue

    return ""


def is_sponsored(driver, element):

    """
    Looks for a 'Sponsored' label only inside this result's own block.
    Stops climbing as soon as a parent contains more than one title
    (so the text of the whole page is not checked).
    """

    try:
        return bool(driver.execute_script("""
            let node = arguments[0];

            for (let i = 0; i < 8 && node.parentElement; i++) {
                const p = node.parentElement;
                const titles = p.querySelectorAll("h3, div[role='heading']");
                if (titles.length > 1) break;
                node = p;
            }

            const lines = (node.innerText || "")
                .toLowerCase()
                .split("\\n")
                .map(l => l.trim());

            return lines.some(l =>
                l === "ad" ||
                l === "ads" ||
                l.startsWith("ad ·") ||
                (l.startsWith("sponsored") && l.length < 40)
            );
        """, element))

    except Exception:
        return False


def is_ad_anchor(driver, anchor):

    """
    If any attribute of an ad's <a> (data-rw, ping, href ...) contains aclk /
    googleadservices / doubleclick / pagead, it is an ad.
    (Mobile ads often link straight to the advertiser, so the href alone is not enough.)
    """

    try:
        return bool(driver.execute_script("""
            const a = arguments[0];

            for (const attr of Array.from(a.attributes)) {

                const v = (attr.value || "").toLowerCase();

                if (
                    v.includes("/aclk") ||
                    v.includes("googleadservices") ||
                    v.includes("doubleclick") ||
                    v.includes("/pagead/")
                ) {
                    return true;
                }
            }

            return false;
        """, anchor))

    except Exception:
        return False


def get_sponsored_regions(driver):

    """
    The part of the page from a 'Sponsored Result' / 'Sponsored' label to 'Hide sponsored result'
    (y-coordinates). Every title inside this range is an ad.
    If there is no hide button, 160px below the label.
    """

    try:
        regions = driver.execute_script("""
            const labels = [
                "sponsored result", "sponsored results", "sponsored",
                "sponsored products", "ads", "ad"
            ];

            const starts = [];
            const ends = [];

            const els = Array.from(
                document.querySelectorAll("div,span,a,button,p,h2,h3")
            );

            for (const el of els) {

                const t = (el.innerText || "").trim().toLowerCase();

                if (!t || t.length > 40) continue;

                if (el.querySelectorAll("*").length > 3) continue;

                const r = el.getBoundingClientRect();

                if (r.width <= 0 || r.height <= 0) continue;

                const top = r.top + window.scrollY;
                const bottom = r.bottom + window.scrollY;

                if (labels.includes(t)) {
                    starts.push(top);
                } else if (t.startsWith("hide sponsored")) {
                    ends.push(bottom);
                }
            }

            starts.sort((a, b) => a - b);
            ends.sort((a, b) => a - b);

            const out = [];

            for (const s of starts) {

                const e = ends.find(x => x > s);

                if (e !== undefined && (e - s) < 2500) {
                    out.push([s, e]);
                } else {
                    out.push([s, s + 160]);
                }
            }

            return out;
        """)

        return [(float(a), float(b)) for a, b in (regions or [])]

    except Exception:
        return []


def in_sponsored_region(y, regions):

    for start, end in regions:

        if start - 5 <= y <= end:
            return True

    return False


def get_section_regions(driver):

    """
    The part of the page covered by a Google section (Short videos, Videos, Images, People also ask ...):
    from the section name (header) to a button such as 'More short videos' / 'More videos' /
    'Show more images'. Returns: [(top, bottom, name), ...]
    The top tabs (All / Images / Videos ...) are not treated as headers.
    """

    try:
        data = driver.execute_script("""
            const names = arguments[0];

            const endPrefixes = [
                "more videos", "more short videos", "more images",
                "show more images", "more places", "more products", "more deals"
            ];

            const els = Array.from(
                document.querySelectorAll("div,span,a,button,p,h2,h3")
            );

            const starts = [];
            const ends = [];

            for (const el of els) {

                const t = (el.innerText || "").trim().toLowerCase();

                if (!t || t.length > 40) continue;

                if (el.querySelectorAll("*").length > 3) continue;

                const r = el.getBoundingClientRect();

                if (r.width <= 0 || r.height <= 0) continue;

                const top = r.top + window.scrollY;
                const bottom = r.bottom + window.scrollY;

                if (names.includes(t)) {

                    // the search-type tabs at the top (All / Images / Videos ...) are not headers
                    if (el.closest('a, [role="tab"], [role="tablist"], nav')) continue;

                    if (top < 120) continue;

                    starts.push([top, t]);

                } else if (endPrefixes.some(p => t.startsWith(p))) {

                    ends.push(bottom);
                }
            }

            starts.sort((a, b) => a[0] - b[0]);
            ends.sort((a, b) => a - b);

            const out = [];

            for (const [s, name] of starts) {

                const e = ends.find(x => x > s);

                if (e !== undefined && (e - s) < 2500) {
                    out.push([s, e, name]);
                } else {
                    out.push([s, s + 350, name]);
                }
            }

            return out;
        """, SKIP_SECTIONS)

        return [(float(a), float(b), str(n)) for a, b, n in (data or [])]

    except Exception:
        return []


def section_name_at(y, regions):

    for start, end, name in regions:

        if start - 5 <= y <= end:
            return name

    return ""


def extract_domain_from_text(text):

    if not text:
        return ""

    try:
        pattern = (
            r'(?<![@\w\.-])'
            r'(?:www\.)?'
            r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
            r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+'
            r'\.[a-zA-Z]{2,63}'
            r'(?![\w\.-])'
        )

        for match in re.findall(pattern, text):

            domain = normalize_domain(match)

            if not is_valid_domain_format(domain):
                continue

            if is_google_domain(domain):
                continue

            return domain

    except Exception:
        pass

    return ""


def get_domain_from_anchor_text(driver, anchor, title):

    """
    A mobile Google result's <a> contains the site name + breadcrumb
    (for example 'gempundit.com › collections').
    Remove the title and take the first domain found in the remaining text.
    """

    try:
        text = driver.execute_script(
            "return arguments[0].innerText || arguments[0].textContent || '';",
            anchor
        ) or ""

        text = text.replace(title, " ")

        return extract_domain_from_text(text)

    except Exception:
        return ""


def get_domain_from_container_text(driver, element, title):

    """
    Extracts the domain from the visible text of the whole result block
    (limited to this title, not reaching other titles).
    """

    try:
        text = driver.execute_script("""
            let node = arguments[0];

            for (let i = 0; i < 8 && node.parentElement; i++) {
                const p = node.parentElement;
                const titles = p.querySelectorAll("h3, div[role='heading']");
                if (titles.length > 1) break;
                node = p;
            }

            return node.innerText || node.textContent || "";
        """, element) or ""

        text = text.replace(title, " ")

        return extract_domain_from_text(text)

    except Exception:
        return ""


# ============================================================
# BLOCK / CAPTCHA
# ============================================================

def google_block_detected(driver):

    try:
        current_url = (driver.current_url or "").lower()

        if "/sorry/" in current_url or "sorry.google" in current_url:
            return True

        body_text = (
            driver.find_element(By.TAG_NAME, "body").text or ""
        ).lower()

        block_texts = [
            "403. that’s an error",
            "403. that's an error",
            "does not have permission to get url",
            "unusual traffic",
            "our systems have detected unusual traffic",
            "verify you are a human",
            "confirm that you're not a robot",
            "not a robot",
            "recaptcha",
        ]

        return any(t in body_text for t in block_texts)

    except Exception:
        return False


def handle_google_block(driver):

    if not google_block_detected(driver):
        return True

    print()
    print("=" * 70)
    print("🛑 GOOGLE BLOCK / CAPTCHA DETECTED")
    print("=" * 70)
    print()
    print("Solve the verification manually in Chrome (if it is visible).")
    print(f"⏳ Waiting {BLOCK_RETRY_DELAY} seconds...")

    time.sleep(BLOCK_RETRY_DELAY)

    if not google_block_detected(driver):
        print("✅ Google access restored.")
        return True

    if os.environ.get("RANK_LAUNCHED"):

        # run_both.py: both scripts share one terminal -> no input(), wait automatically
        print(
            f"👉 Solve the verification in Chrome. "
            f"It will keep checking by itself for {BLOCK_AUTO_WAIT_SECONDS} sec..."
        )

        waited = 0

        while waited < BLOCK_AUTO_WAIT_SECONDS:

            time.sleep(3)

            waited += 3

            if not google_block_detected(driver):

                print("✅ Google block cleared.")

                time.sleep(2)

                return True

        print("❌ Google block is still active.")

        return False

    try:
        input("Press ENTER after Google access is restored...")
    except Exception:
        time.sleep(10)

    time.sleep(2)

    if google_block_detected(driver):
        print("❌ Google block is still active.")
        return False

    print("✅ Google block cleared.")
    return True


# ============================================================
# CONSENT
# ============================================================

def handle_google_consent(driver):

    try:
        lower = ("translate(normalize-space(.),"
                 "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')")

        xpath = (
            f"//button[contains({lower},'accept all') "
            f"or contains({lower},'i agree') "
            f"or contains({lower},'agree')]"
        )

        for button in driver.find_elements(By.XPATH, xpath):

            try:
                if is_visible(driver, button):

                    driver.execute_script("arguments[0].click();", button)

                    time.sleep(1)

                    print("✅ Google consent handled.")

                    return True

            except Exception:
                continue

    except Exception:
        pass

    return False


# ============================================================
# EXTRACT ORGANIC RESULTS
# ============================================================

def wait_for_search_results(driver, timeout=RESULT_WAIT):

    try:
        WebDriverWait(driver, timeout).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, TITLE_CSS)) > 0
        )
        return True

    except Exception:
        return False


def get_excluded_section(driver, element):

    """
    Name of the Google section (AI Overview, Videos ...) if the title is inside one.
    Returns the name of the excluded section (AI Overview, Videos ...) if the title is inside one.
    """

    try:
        return driver.execute_script("""
            const names = arguments[1];
            let node = arguments[0];

            const docH = Math.max(
                document.body.scrollHeight,
                document.documentElement.scrollHeight
            );

            for (let i = 0; i < 14 && node.parentElement; i++) {

                node = node.parentElement;

                const r = node.getBoundingClientRect();

                if (r.height > docH * 0.5) break;

                const lines = (node.innerText || "")
                    .split("\\n")
                    .map(l => l.trim().toLowerCase())
                    .filter(l => l.length > 0);

                for (const l of lines.slice(0, 2)) {
                    if (names.includes(l)) return l;
                }
            }

            return "";
        """, element, SKIP_SECTIONS) or ""

    except Exception:
        return ""


def get_block_lines(driver, element):

    """
    Lines of visible text of the title's result block (does not climb up to other titles).
    The text inside the anchor is included as well.
    """

    try:
        lines = driver.execute_script("""
            const el = arguments[0];

            let node = el;

            for (let i = 0; i < 8 && node.parentElement; i++) {
                const p = node.parentElement;
                const titles = p.querySelectorAll("h3, div[role='heading']");
                if (titles.length > 1) break;
                node = p;
            }

            const out = [];

            const anchor = el.closest("a");

            if (anchor) {
                out.push(...(anchor.innerText || anchor.textContent || "").split("\\n"));
            }

            out.push(...(node.innerText || node.textContent || "").split("\\n"));

            return out.map(l => l.trim()).filter(l => l.length > 0);
        """, element)

        return lines or []

    except Exception:
        return []


URL_LINE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?"
    r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,63})"
    r"(?:[/\s›].*)?$",
    re.IGNORECASE
)


def get_displayed_domain(lines):

    """
    An organic result has, above the title next to the site name,
    a line like 'https://www.gempundit.com' or 'gempundit.com › page'.
    Organic social media results (YouTube, Instagram, Facebook ...) can have it as well.
    """

    for line in lines:

        low = line.lower()

        if not (low.startswith("http://") or low.startswith("https://") or "›" in line):
            continue

        match = URL_LINE_RE.match(line)

        if not match:
            continue

        domain = normalize_domain(match.group(1))

        if is_valid_domain_format(domain) and not is_google_domain(domain):
            return domain

    return ""


# Social media: organic results of these domains often have no 'https://...' line,
# only a line such as 'Facebook · Page name' / 'YouTube · Channel'.
SOCIAL_DOMAINS = [
    "facebook.com", "fb.com", "instagram.com", "youtube.com", "youtu.be",
    "twitter.com", "x.com", "linkedin.com", "pinterest.com", "reddit.com",
    "quora.com", "tiktok.com", "threads.net", "tumblr.com", "medium.com",
    "snapchat.com", "t.me", "telegram.me", "wa.me",
]

PLATFORM_DOMAINS = {
    "facebook": "facebook.com",
    "youtube": "youtube.com",
    "instagram": "instagram.com",
    "x": "x.com",
    "twitter": "twitter.com",
    "linkedin": "linkedin.com",
    "pinterest": "pinterest.com",
    "reddit": "reddit.com",
    "quora": "quora.com",
    "tiktok": "tiktok.com",
    "threads": "threads.net",
    "tumblr": "tumblr.com",
    "medium": "medium.com",
}

PLATFORM_LINE_RE = re.compile(
    r"^(facebook|youtube|instagram|x|twitter|linkedin|pinterest|reddit|quora|"
    r"tiktok|threads|tumblr|medium)\s*[·•]",
    re.IGNORECASE
)

# Titles skipped in the last search (element, reason) -> orange badge in the screenshot
LAST_SKIPPED = []


def is_social_domain(domain):

    if not domain:
        return False

    domain = normalize_domain(domain)

    return any(domain == s or domain.endswith("." + s) for s in SOCIAL_DOMAINS)


def get_platform_domain(lines):

    """'Facebook · Geological Survey of India' -> facebook.com"""

    for line in lines[:8]:

        match = PLATFORM_LINE_RE.match(line.strip())

        if match:
            return PLATFORM_DOMAINS.get(match.group(1).lower(), "")

    return ""


def read_title_text(driver, element):

    """Selenium .text is sometimes empty (rendering) -> read it through JS."""

    try:
        text = driver.execute_script(
            "return (arguments[0].innerText || arguments[0].textContent || '').trim();",
            element
        )

        if text:
            return text

    except Exception:
        pass

    try:
        return (element.text or "").strip()
    except Exception:
        return ""


def find_carousel_titles(driver, titles, top_of):

    """
    2+ titles in the same row (same y) that have no domain line above them
    = carousel cards (Short videos, Videos, Popular products, Deals ...).
    A normal organic result list has only one title per row.
    """

    items = []

    for element in titles:

        try:
            if not read_title_text(driver, element):
                continue

            if not is_visible(driver, element):
                continue

            y = top_of.get(id(element))

            if y is None:
                continue

            if get_displayed_domain(get_block_lines(driver, element)):
                continue

            items.append((id(element), y))

        except Exception:
            continue

    carousel = set()

    for i, (key_a, y_a) in enumerate(items):

        for j, (key_b, y_b) in enumerate(items):

            if i != j and abs(y_a - y_b) <= 8:
                carousel.add(key_a)
                break

    return carousel


def extract_organic_results(driver):

    """
    All organic results on the page from top to bottom (social media included).
    Skipped: Sponsored/Ads and Google's own sections (AI Overview, Videos ...).
    """

    results = []
    seen_domains = set()

    skipped = LAST_SKIPPED
    del skipped[:]

    def skip(element, index, reason, short):

        print(f"   ✗ #{index} skip ({reason}) | {short}")

        skipped.append((element, reason))

    try:
        titles = driver.find_elements(By.CSS_SELECTOR, TITLE_CSS)
    except Exception:
        titles = []

    # Sort by the real position on the page (top to bottom)
    top_of = {}

    try:
        tops = driver.execute_script(
            "return arguments[0].map(e => "
            "e.getBoundingClientRect().top + window.scrollY);",
            titles
        )

        top_of = {id(t): y for y, t in zip(tops, titles)}

        titles = [t for _, t in sorted(
            zip(tops, titles), key=lambda x: x[0]
        )]

    except Exception:
        pass

    sponsored_regions = get_sponsored_regions(driver)

    section_regions = []

    carousel_titles = set()

    if USE_SECTION_FILTER:
        section_regions = get_section_regions(driver)
        carousel_titles = find_carousel_titles(driver, titles, top_of)

    print(f"🔎 Candidate titles: {len(titles)}")

    for index, title_el in enumerate(titles, start=1):

        if len(results) >= MAX_ORGANIC_RESULTS:
            break

        try:
            title = read_title_text(driver, title_el)

            if not title:
                continue

            short = title[:50]

            if not is_visible(driver, title_el):
                continue

            try:
                anchor = title_el.find_element(By.XPATH, "./ancestor::a[1]")
            except Exception:
                skip(title_el, index, "no link", short)
                continue

            href = get_anchor_href(anchor)

            if not href:
                continue

            # ---- Sponsored / Ads: marked as AD, NOT counted ----
            if (
                "/aclk" in href
                or "googleadservices" in href
                or is_ad_anchor(driver, anchor)
            ):
                skip(title_el, index, "AD: ad link", short)
                continue

            if is_sponsored(driver, title_el):
                skip(title_el, index, "AD: sponsored label", short)
                continue

            title_y = top_of.get(id(title_el))

            if title_y is not None and in_sponsored_region(title_y, sponsored_regions):
                skip(title_el, index, "AD: sponsored result block", short)
                continue

            # ---- Domain: taken from the domain line written above the title ----
            lines = get_block_lines(driver, title_el)

            domain = get_displayed_domain(lines)

            url = extract_url_from_google_href(href)

            note = ""

            if not domain:

                # Title without a domain line: first check whether it belongs to one of Google's own
                # sections (AI Overview, Videos, Images ...)
                if USE_SECTION_FILTER:

                    section = ""

                    # 1) inside a section (from the header to the 'More ...' button)
                    if title_y is not None:
                        section = section_name_at(title_y, section_regions)

                    # 2) several cards in the same row = carousel
                    if not section and id(title_el) in carousel_titles:
                        section = "carousel"

                    # 3) section name in the first lines of an ancestor
                    if not section:
                        section = get_excluded_section(driver, title_el)

                    if section:
                        skip(title_el, index, f"Google section: {section}", short)
                        continue

                href_domain = get_full_domain(url) if url else ""

                if href_domain and (
                    not is_valid_domain_format(href_domain)
                    or is_google_domain(href_domain)
                ):
                    href_domain = ""

                platform_domain = get_platform_domain(lines)

                tag = ""

                try:
                    tag = (title_el.tag_name or "").lower()
                except Exception:
                    pass

                if is_social_domain(href_domain):
                    domain = href_domain
                    note = "  (social)"

                elif platform_domain:
                    domain = platform_domain
                    note = "  (social)"

                elif ACCEPT_H3_WITHOUT_DOMAIN_LINE and tag == "h3" and href_domain:
                    domain = href_domain
                    note = "  (h3 link)"

            if not domain:
                skip(title_el, index, "domain not found", short)
                continue

            if (
                not is_valid_domain_format(domain)
                or is_google_domain(domain)
                or is_skipped_domain(domain)
            ):
                skip(title_el, index, f"invalid domain {domain}", short)
                continue

            if domain in seen_domains:
                skip(title_el, index, f"duplicate {domain}", short)
                continue

            seen_domains.add(domain)

            results.append({
                "title": title,
                "url": url,
                "domain": domain,
                "element": title_el,
            })

            print(f"   ✓ Organic {len(results)}: {domain} | {short}{note}")

        except Exception as e:
            print(f"   ⚠️ Title {index} error: {e}")
            continue

    print(f"🔎 Valid organic results: {len(results)}")

    return results


def save_debug(driver, keyword):

    if not DEBUG_ON_EMPTY:
        return

    try:
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", keyword)[:40]
        stamp = int(time.time())

        html_path = os.path.join(BASE_PATH, f"debug_mobile_{safe}_{stamp}.html")
        png_path = os.path.join(BASE_PATH, f"debug_mobile_{safe}_{stamp}.png")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)

        driver.save_screenshot(png_path)

        print(f"🐞 Debug saved: {html_path}")

    except Exception as e:
        print(f"⚠️ Debug save error: {e}")


# ============================================================
# SEARCH BOX HELPERS (for the mobile layout)
# ============================================================

def dismiss_popups(driver):

    """Close bottom-sheet popups such as Sign-in / 'No thanks' / 'Not now'."""

    try:
        lower = ("translate(normalize-space(.),"
                 "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')")

        xpath = (
            f"//*[self::button or @role='button'][contains({lower},'no thanks') "
            f"or contains({lower},'not now') "
            f"or contains({lower},'stay signed out') "
            f"or contains({lower},'dismiss') "
            f"or contains({lower},'reject all')]"
        )

        for el in driver.find_elements(By.XPATH, xpath):

            try:
                if is_visible(driver, el):
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(1)
                    print("✅ Popup dismissed.")
                    return True
            except Exception:
                continue

    except Exception:
        pass

    return False


def find_visible_search_box(driver, timeout=8):

    end = time.time() + timeout

    while time.time() < end:

        try:
            for el in driver.find_elements(
                By.CSS_SELECTOR, "textarea[name='q'], input[name='q']"
            ):
                try:
                    if el.is_displayed() and el.is_enabled() and is_visible(driver, el):
                        return el
                except Exception:
                    continue
        except Exception:
            pass

        time.sleep(0.5)

    return None


def open_mobile_search_box(driver):

    """Some mobile layouts require tapping the search bar first."""

    triggers = [
        "form[role='search']",
        "div[role='search']",
        "[aria-label='Search']",
        "[aria-label='Search Google']",
        "textarea[name='q']",
        "input[name='q']",
    ]

    for css in triggers:

        try:
            for el in driver.find_elements(By.CSS_SELECTOR, css):
                try:
                    if is_visible(driver, el):
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(1)
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    return False


def type_and_submit(driver, box, keyword):

    """Type the keyword and press Enter. True = submitted."""

    try:
        try:
            box.click()
        except Exception:
            driver.execute_script("arguments[0].click();", box)

        try:
            box.clear()
        except Exception:
            pass

        box.send_keys(keyword)

        time.sleep(0.7)

        box.send_keys(Keys.ENTER)

        return True

    except Exception as e:

        print(f"⚠️ Normal typing failed ({type(e).__name__}). Trying through JS...")

    try:
        driver.execute_script("""
            const el = arguments[0];
            el.focus();
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            if (el.form) { el.form.submit(); }
        """, box, keyword)

        return True

    except Exception as e:

        print(f"⚠️ JS typing failed too: {e}")

        return False


def go_direct_search(driver, keyword):

    """Last fallback: direct search URL."""

    print("↪️ Fallback: using the direct search URL.")

    try:
        driver.get(
            GOOGLE_HOME + "search?q=" + quote_plus(keyword) + "&hl=en&gl=in"
        )
    except Exception:
        pass


# ============================================================
# SEARCH (homepage + search box, NOT the direct /search?q= URL)
# ============================================================

def search_keyword(driver, keyword):

    print()
    print(f"🔍 Searching Google (mobile): {keyword}")

    try:
        driver.get(GOOGLE_HOME)

        time.sleep(2)

        handle_google_consent(driver)

        if google_block_detected(driver):
            if not handle_google_block(driver):
                return []

        dismiss_popups(driver)

        search_box = find_visible_search_box(driver, 6)

        if search_box is None:

            print("⚠️ Search box not visible, trying to tap it...")

            open_mobile_search_box(driver)

            search_box = find_visible_search_box(driver, 6)

        submitted = False

        if search_box is not None:
            submitted = type_and_submit(driver, search_box, keyword)

        if not submitted:

            print(f"   URL: {driver.current_url}")

            save_debug(driver, keyword + "_searchbox")

            go_direct_search(driver, keyword)

        time.sleep(2.5)

        if google_block_detected(driver):
            print("🛑 Google blocked this search.")
            handle_google_block(driver)
            return []

        handle_google_consent(driver)

        if not wait_for_search_results(driver, RESULT_WAIT):
            print("⚠️ Result titles not detected.")
            save_debug(driver, keyword)
            return []

        if google_block_detected(driver):
            print("🛑 Google block detected after results load.")
            return []

        time.sleep(1.5)

        # Let the page load fully (lazy content/images) -> screenshot and data come from the same page
        wait_page_fully_loaded(driver)

        results = extract_organic_results(driver)

        if not results:
            save_debug(driver, keyword)

        return results

    except TimeoutException:
        print("⚠️ Google search timeout.")
        return []

    except WebDriverException as e:
        print(f"⚠️ Browser error: {e}")
        return []

    except Exception as e:
        print(f"⚠️ Search error: {e}")
        return []


# ============================================================
# DRIVER
# ============================================================

def build_options(custom_device=False, profile=CHROME_PROFILE):

    options = Options()

    options.page_load_strategy = "eager"

    if custom_device:
        options.add_experimental_option("mobileEmulation", {
            "deviceMetrics": {
                "width": 412,
                "height": 915,
                "pixelRatio": 2.625
            },
            "userAgent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Mobile Safari/537.36"
            )
        })
    else:
        options.add_experimental_option(
            "mobileEmulation", {"deviceName": "Pixel 7"}
        )

    options.add_argument(f"--user-data-dir={profile}")
    options.add_argument("--lang=en-IN")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-component-update")
    options.add_argument("--disable-default-apps")

    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)

    return options


def kill_profile_chrome(profile):

    """
    Closes only the Chrome that was opened from this bot's profile folder
    (your normal Chrome is not closed). Windows only.
    """

    if os.name != "nt":
        return

    try:
        name = os.path.basename(profile.rstrip("\\/"))

        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            f"Where-Object {{ $_.CommandLine -like '*{name}*' }} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )

        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=30
        )

        time.sleep(2)

    except Exception:
        pass


def kill_old_chromedriver():

    """
    Intentionally does nothing: the desktop script may be running at the same time,
    so we cannot kill every chromedriver.exe.
    """

    return


def create_driver():

    print()
    print("🚀 Starting Chrome Mobile (Pixel 7)...")

    # Remove a leftover bot Chrome (profile lock)
    kill_profile_chrome(CHROME_PROFILE)
    kill_old_chromedriver()

    temp_profile = tempfile.mkdtemp(prefix="RankBotMobile_")

    attempts = [
        ("Pixel 7 (deviceName), saved profile", False, CHROME_PROFILE),
        ("Custom Pixel-like device, saved profile", True, CHROME_PROFILE),
        ("Pixel 7 (deviceName), FRESH temp profile", False, temp_profile),
    ]

    driver = None

    last_error = None

    for label, custom, profile in attempts:

        try:
            print(f"   ▶ Try: {label}")

            driver = webdriver.Chrome(options=build_options(custom, profile))

            break

        except Exception as e:

            last_error = e

            print(f"   ⚠️ Fail: {str(e).splitlines()[0]}")

            # On failure, close the window that was left open
            kill_profile_chrome(profile)
            kill_old_chromedriver()

    if driver is None:

        shutil.rmtree(temp_profile, ignore_errors=True)

        print()
        print("❌ Chrome could not start. Please:")
        print("   1) Close chrome.exe / chromedriver.exe in Task Manager")
        print("   2) Update Chrome (chrome://settings/help)")
        print("   3) pip install -U selenium")

        raise last_error

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(10)

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(
                    navigator, 'webdriver', { get: () => undefined }
                );
                """
            }
        )
    except Exception:
        pass

    print("✅ Chrome Mobile started.")

    return driver


# ============================================================
# SAVE / LOAD
# ============================================================

COLUMNS = ["Keyword", "GemPundit Rank", "Top Competitor"]


def save_data(data):

    try:
        df = pd.DataFrame(data)

        for column in COLUMNS:
            if column not in df.columns:
                df[column] = ""

        df = df[COLUMNS].drop_duplicates(subset=["Keyword"], keep="last")

        df.to_csv(OUTPUT_FILE_CSV, index=False, encoding="utf-8-sig")

        # In combined mode (run_both.py) only the combined Excel is created;
        # when run alone, the script writes its own Excel.
        if not os.environ.get("RANK_LAUNCHED"):
            df.to_excel(OUTPUT_FILE_XLSX, index=False)

        print("💾 Data saved.")

    except Exception as e:
        print(f"⚠️ Save error: {e}")


def load_previous_data():

    results = []
    done_keywords = set()

    if not os.path.exists(OUTPUT_FILE_CSV):
        return results, done_keywords

    try:
        modified_day = datetime.fromtimestamp(
            os.path.getmtime(OUTPUT_FILE_CSV)
        ).date()

        if not RESUME_SAME_DAY or modified_day != date.today():

            print()
            print("🆕 Fresh run (old data is not from today / resume is off).")

            return results, done_keywords

        old_df = pd.read_csv(OUTPUT_FILE_CSV)

        if "Keyword" not in old_df.columns:
            return results, done_keywords

        # Error rows will be retried
        if "GemPundit Rank" in old_df.columns:
            valid = old_df[
                old_df["GemPundit Rank"].astype(str).str.strip().ne("Error")
            ].copy()
        else:
            valid = old_df.copy()

        results = valid.fillna("").to_dict("records")

        done_keywords = set(valid["Keyword"].astype(str).str.strip().tolist())

        print()
        print("🔄 Resuming today's data...")
        print(f"   Already completed: {len(done_keywords)}")

    except Exception as e:
        print(f"⚠️ Previous CSV error: {e}")

    return results, done_keywords


def remove_keyword(results, keyword):

    return [
        row for row in results
        if str(row.get("Keyword", "")).strip() != keyword
    ]


# ============================================================
# AUTO CLEANUP (old data is deleted automatically)
# ============================================================

def cleanup_old_data(protect_recent=True):

    """
    Deletes old data when a run starts:
      * google_rank_desktop / mobile / combined  (.xlsx, .csv), debug_mobile_* files
      * Screenshots\\\\<DD-MM-YYYY> folders
    CLEAN_EVERY_RUN = True  -> ALL previous data (including today's) is deleted, fresh start
    CLEAN_EVERY_RUN = False -> only yesterday or older
    No other file (keywords.txt, scripts) is touched.
    """

    if not AUTO_DELETE_OLD_DATA:
        return

    # run_both.py has already cleaned up (both scripts run together)
    if os.environ.get("RANK_LAUNCHED"):
        return

    today = date.today()

    now = time.time()

    removed = []

    def is_recent(path):

        # If another script is running in this folder right now, do not delete its files
        return protect_recent and (now - os.path.getmtime(path)) < RECENT_PROTECT_SECONDS

    def old_enough(day):

        return CLEAN_EVERY_RUN or day < today

    # ---- Excel / CSV / debug / marker files ---------------------
    names = [
        "google_rank_desktop.xlsx",
        "google_rank_desktop_live.csv",
        "google_rank_mobile.xlsx",
        "google_rank_mobile_live.csv",
        "google_rank_combined.xlsx",
        ".done_desktop",
        ".done_mobile",
    ]

    try:
        for name in os.listdir(BASE_PATH):
            if name.startswith("debug_mobile_") or name.startswith("debug_desktop_"):
                names.append(name)
    except Exception:
        pass

    for name in names:

        path = os.path.join(BASE_PATH, name)

        try:
            if not os.path.isfile(path):
                continue

            day = datetime.fromtimestamp(os.path.getmtime(path)).date()

            if old_enough(day) and not is_recent(path):
                os.remove(path)
                removed.append(name)

        except FileNotFoundError:
            continue  # the other script already removed it

        except Exception as e:
            print(f"⚠️ Could not delete ({name}): {e}")

    # ---- Screenshot date folders --------------------------------
    root = os.path.join(BASE_PATH, "Screenshots")

    if os.path.isdir(root):

        for entry in os.listdir(root):

            folder = os.path.join(root, entry)

            if not os.path.isdir(folder):
                continue

            try:
                folder_day = datetime.strptime(entry, "%d-%m-%Y").date()
            except ValueError:
                continue  # not a date folder -> leave it alone

            try:
                if old_enough(folder_day) and not is_recent(folder):
                    shutil.rmtree(folder)
                    removed.append(f"Screenshots\\\\{entry}")

            except FileNotFoundError:
                continue  # the other script already removed it

            except Exception as e:
                print(f"⚠️ Could not delete folder ({entry}): {e}")

    if removed:
        print()
        print("🧹 Old data deleted:")
        for item in removed:
            print(f"   - {item}")


def relative_shot(path):

    """Short path for the Excel: Screenshots\\22-10-2026\\mobile\\001_x.png"""

    if not path:
        return ""

    try:
        return os.path.relpath(path, BASE_PATH)
    except Exception:
        return path


# ============================================================
# MAIN
# ============================================================

def run_mobile():

    print()
    print("=" * 70)
    print("📱 GOOGLE RANK TRACKER (MOBILE)")
    print("=" * 70)

    if not os.path.exists(INPUT_FILE):
        print("❌ keywords.txt not found:")
        print(INPUT_FILE)
        return

    cleanup_old_data()

    # Split terminals (VS Code task): if both start together Google would see a burst:
    # the task can set RANK_START_DELAY in its env (10 sec for mobile)
    try:
        start_delay = int(os.environ.get("RANK_START_DELAY", "0"))
    except ValueError:
        start_delay = 0

    if start_delay > 0:
        print(f"⏳ Starting in {start_delay} sec (so both scripts do not hit Google together)...")
        time.sleep(start_delay)

    shot_dir = ""

    if TAKE_SCREENSHOTS:
        shot_dir = get_screenshot_folder(BASE_PATH, "mobile")
        print(f"📸 Screenshots folder: {shot_dir}")

    driver = None

    try:
        driver = create_driver()

        try:
            driver.get(GOOGLE_HOME)
        except Exception:
            pass

        time.sleep(2)

        handle_google_consent(driver)

        if google_block_detected(driver):
            if not handle_google_block(driver):
                print("❌ Google access is blocked.")
                return

        results, done_keywords = load_previous_data()

        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]

        keywords = list(dict.fromkeys(keywords))

        total_keywords = len(keywords)

        print()
        print(f"📊 Total Keywords: {total_keywords}")

        for idx, keyword in enumerate(keywords, start=1):

            if keyword in done_keywords:
                print()
                print(f"⏭️ ({idx}/{total_keywords}) Already completed: {keyword}")
                continue

            print()
            print("=" * 70)
            print(f"📱 ({idx}/{total_keywords}) Searching: {keyword}")
            print("=" * 70)

            organic_results = search_keyword(driver, keyword)

            # --------------------------------------------
            # Screenshot (full page, of the same page the data came from)
            # --------------------------------------------

            shot_path = ""

            if TAKE_SCREENSHOTS:

                if organic_results:
                    status = "OK"
                elif google_block_detected(driver):
                    status = "BLOCKED"
                else:
                    status = "NORESULTS"

                shot_path = capture_keyword_screenshot(
                    driver,
                    shot_dir,
                    idx,
                    keyword,
                    organic_results,
                    TARGET_DOMAIN,
                    status,
                    ANNOTATE_SCREENSHOTS
                )

            shot_name = relative_shot(shot_path)

            # --------------------------------------------
            # No results / blocked
            # --------------------------------------------

            if not organic_results:

                print("❌ No valid organic results found.")

                results = remove_keyword(results, keyword)

                results.append({
                    "Keyword": keyword,
                    "GemPundit Rank": "Error",
                    "Top Competitor": "N/A",
                })

                save_data(results)

                if google_block_detected(driver):
                    print()
                    print("🛑 Google is still blocking requests.")
                    print("⏸️ Stopping current run safely.")
                    break

                time.sleep(random.uniform(MIN_SEARCH_DELAY, MAX_SEARCH_DELAY))

                continue

            # --------------------------------------------
            # Print results
            # --------------------------------------------

            print()
            print("----- ORGANIC RESULTS -----")

            for rank, item in enumerate(organic_results, start=1):
                print(f"{rank}. {item['domain']}")

            print("---------------------------")

            # --------------------------------------------
            # Rank
            # --------------------------------------------

            gempundit_rank = None

            for rank, item in enumerate(organic_results, start=1):

                domain = normalize_domain(item.get("domain", ""))

                if _matches(domain, TARGET_DOMAIN):
                    gempundit_rank = rank
                    break

            competitor = organic_results[0].get("domain", "N/A")

            # GemPundit not found on the first page -> 10+
            if gempundit_rank is None:

                gempundit_rank = "10+"

                if LAST_UNREADABLE > 0:
                    print(
                        f"⚠️ The domain of {LAST_UNREADABLE} link(s) "
                        f"could not be read, so 10+ may be wrong because of them."
                    )

            results = remove_keyword(results, keyword)

            results.append({
                "Keyword": keyword,
                "GemPundit Rank": gempundit_rank,
                "Top Competitor": "" if gempundit_rank == 1 else competitor,
            })

            save_data(results)

            done_keywords.add(keyword)

            print()
            print(f"🎯 GemPundit Rank: {gempundit_rank}")
            print(f"🏆 Top Competitor: {competitor}")

            delay = random.uniform(MIN_SEARCH_DELAY, MAX_SEARCH_DELAY)

            print(f"⏳ Next search in {delay:.1f} seconds...")

            time.sleep(delay)

    except KeyboardInterrupt:
        print()
        print("⛔ Script stopped manually.")
        print("💾 Existing data has already been saved.")

    except Exception as e:
        print()
        print(f"❌ MAIN ERROR: {e}")

    finally:

        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        print()
        print("=" * 70)
        print("✅ MOBILE COMPLETED")
        print("=" * 70)


if __name__ == "__main__":

    run_mobile()

    # Tell run_both.py that this script is done (it will build the combined Excel)
    done_file = os.environ.get("RANK_DONE_FILE")

    if done_file:
        try:
            open(done_file, "w").close()
        except Exception:
            pass
