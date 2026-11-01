"""
screenshot_utils.py
-------------------
Desktop aur Mobile dono rank scripts ke liye shared helpers:

  * wait_page_fully_loaded()  -> page poora load hone tak wait (lazy images bhi)
  * annotate_results()        -> counted results par #rank badge (Excel se match karne ke liye)
  * take_full_page_screenshot()-> poore page ka screenshot, upar se neeche,
                                  bina cut / bina overlap (chunks me capture + stitch)
  * capture_keyword_screenshot() -> upar ke sab ek saath

Zaroori: pip install pillow
"""

import io
import os
import re
import time
import math
import base64
import unicodedata

from datetime import datetime

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


# ============================================================
# CONFIG
# ============================================================

# Page ki max height (CSS px). Isse lamba page kaata jayega (infinite scroll se bachne ke liye)
MAX_PAGE_HEIGHT = 20000

# Ek baar me kitni height capture karni hai (CSS px). Chhota rakha hai taaki
# Chrome ki texture limit (~16384 px) se screenshot kabhi cut na ho.
CHUNK_HEIGHT = 2500


# ============================================================
# FILE / FOLDER
# ============================================================

def safe_filename(text, max_len=60):

    """
    Windows-safe filename. Hindi/Unicode letters aur matras (ु, ्, ा ...) rakhta hai,
    baaki symbols ko '_' bana deta hai.
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


def wait_page_fully_loaded(driver, log=print):

    """
    1) readyState == complete
    2) neeche tak scroll (lazy-load content/images trigger karne ke liye)
    3) saari visible images load hone tak wait
    4) wapas top par aao, page height stable hone tak wait
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

def annotate_results(driver, results, target_domain, log=print):

    """
    Har counted organic result ke title par '#<rank> <domain>' badge + outline.
    Target domain (gempundit) green, baaki red.
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
            # element stale ho gaya to annotation skip (screenshot phir bhi lega)
            continue


# ============================================================
# FULL PAGE SCREENSHOT
# ============================================================

def _hide_fixed(driver, keep_top):

    """
    position: fixed / sticky elements ko chhupao taaki chunks me wo
    baar-baar na aayein (overlap/ghost header se bachne ke liye).
    keep_top=True : sirf page ke top wale header ko dikhne do (pehle chunk me).
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
    Poore page ka screenshot (upar se neeche). Chrome CDP se chunks me capture karke
    Pillow se jodta hai -> koi hissa cut/overlap nahi.
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
        log("⚠️ Page size read nahi hua, screenshot skip.")
        return False

    if full_height > MAX_PAGE_HEIGHT:
        log(f"⚠️ Page bahut lamba ({full_height}px). {MAX_PAGE_HEIGHT}px tak capture hoga.")

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

        log("⚠️ Pillow install nahi hai (pip install pillow). Chunks alag-alag save ho rahe hain.")

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
    Return: saved file ka full path, fail par "".
    """

    try:
        if annotate and organic_results:
            annotate_results(driver, organic_results, target_domain, log)

        name = f"{index:03d}_{safe_filename(keyword)}"

        if status and status != "OK":
            name += f"_{status}"

        path = unique_path(folder, name)

        if take_full_page_screenshot(driver, path, log):
            return path

    except Exception as e:

        log(f"⚠️ Screenshot error: {e}")

    return ""
