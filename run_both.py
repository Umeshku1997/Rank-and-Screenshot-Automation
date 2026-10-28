"""
run_both.py
-----------
Runs the Desktop and Mobile rank trackers TOGETHER
(separate Chrome browsers, output in this same VS Code terminal)
and writes the results of both into ONE Excel file:

    google_rank_combined.xlsx

    Keyword | Mobile | Who is on First | Desktop | Who is on First

Every terminal line is prefixed with [DESKTOP] / [MOBILE ].

Use:
    python run_both.py            -> prepares the VS Code task for TWO separate split terminals
                                     (then press Ctrl+Shift+B: left = Desktop, right = Mobile,
                                      and the combined Excel is built automatically afterwards)
    python run_both.py together   -> both in ONE terminal (with prefixes) + combined Excel
    python run_both.py desktop    -> desktop only
    python run_both.py mobile     -> mobile only
    python run_both.py combine    -> build the combined Excel from the desktop + mobile live CSV files

To run only one of them, you can also run desktop_rank.py or mobile_rank.py directly.
Press Ctrl+C in the terminal to stop.
"""

import os
import sys
import csv
import time
import shutil
import subprocess
import threading

from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.utils import get_column_letter


# This must be the same folder as BASE_PATH in desktop_rank.py / mobile_rank.py
BASE = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = {
    "desktop": "desktop_rank.py",
    "mobile": "mobile_rank.py",
}

KEYWORDS_FILE = os.path.join(BASE, "keywords.txt")

LIVE_CSV = {
    "desktop": os.path.join(BASE, "google_rank_desktop_live.csv"),
    "mobile": os.path.join(BASE, "google_rank_mobile_live.csv"),
}

COMBINED_FILE = os.path.join(BASE, "google_rank_combined.xlsx")

HEADERS = ["Keyword", "Mobile", "Who is on First", "Desktop", "Who is on First"]

# True  = delete ALL previous data (Excel, CSV, Screenshots) on EVERY run -> fresh start, new files.
# False = delete only data from yesterday or older (today's data is kept).
AUTO_DELETE_OLD_DATA = True
CLEAN_EVERY_RUN = True

# Only relevant when CLEAN_EVERY_RUN = False: today's leftover data is resumed.
RESUME_SAME_DAY = False  # (only used by the scripts)

# Files modified by another script within this many seconds are not deleted
# (so two scripts running side by side do not delete each other's data)
RECENT_PROTECT_SECONDS = 90

# Mobile starts a bit later so Google does not see a burst when both start together
STAGGER_SECONDS = 10

# While running, the combined Excel is refreshed every this many seconds
REFRESH_SECONDS = 15


# ============================================================
# COMBINED EXCEL
# ============================================================

def read_keywords():

    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]

    return list(dict.fromkeys(keywords))


def read_live_csv(path):

    """
    {keyword: (rank, competitor)}  -- today's data only (old data is never mixed in).
    """

    data = {}

    if not os.path.exists(path):
        return data

    try:
        modified = datetime.fromtimestamp(os.path.getmtime(path)).date()

        if modified != date.today():
            return data

        with open(path, "r", encoding="utf-8-sig", newline="") as f:

            for row in csv.DictReader(f):

                keyword = (row.get("Keyword") or "").strip()

                if not keyword:
                    continue

                data[keyword] = (
                    (row.get("GemPundit Rank") or "").strip(),
                    (row.get("Top Competitor") or "").strip(),
                )

    except Exception:
        pass

    return data


def rank_cell(rank):

    """'3' -> 3 (number), '10+' / 'Error' -> text, missing -> ''."""

    rank = str(rank).strip()

    if not rank:
        return ""

    try:
        number = float(rank)

        if number.is_integer():
            return int(number)

    except ValueError:
        pass

    return rank


def first_cell(rank, competitor):

    """Blank if the rank is 1 (or Error / missing), otherwise the competitor name."""

    rank = str(rank).strip()

    if not rank or rank == "Error":
        return ""

    if rank_cell(rank) == 1:
        return ""

    if competitor.strip().upper() == "N/A":
        return ""

    return competitor.strip()


def build_combined():

    """Merge both live CSV files into one plain Excel (no colors). True = created."""

    try:
        keywords = read_keywords()
    except Exception:
        return False

    desktop = read_live_csv(LIVE_CSV["desktop"])
    mobile = read_live_csv(LIVE_CSV["mobile"])

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Rank"

    sheet.append(HEADERS)

    for keyword in keywords:

        m_rank, m_comp = mobile.get(keyword, ("", ""))
        d_rank, d_comp = desktop.get(keyword, ("", ""))

        sheet.append([
            keyword,
            rank_cell(m_rank),
            first_cell(m_rank, m_comp),
            rank_cell(d_rank),
            first_cell(d_rank, d_comp),
        ])

    widths = [28, 10, 26, 10, 26]

    for number, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(number)].width = width

    try:
        workbook.save(COMBINED_FILE)

    except PermissionError:
        # The Excel file is open -> it will be retried on the next refresh
        return False

    except Exception:
        return False

    return True


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
        for name in os.listdir(BASE):
            if name.startswith("debug_mobile_") or name.startswith("debug_desktop_"):
                names.append(name)
    except Exception:
        pass

    for name in names:

        path = os.path.join(BASE, name)

        try:
            if not os.path.isfile(path):
                continue

            day = datetime.fromtimestamp(os.path.getmtime(path)).date()

            if old_enough(day) and not is_recent(path):
                os.remove(path)
                removed.append(name)

        except Exception as e:
            print(f"⚠️ Could not delete ({name}): {e}")

    # ---- Screenshot date folders --------------------------------
    root = os.path.join(BASE, "Screenshots")

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

            except Exception as e:
                print(f"⚠️ Could not delete folder ({entry}): {e}")

    if removed:
        print()
        print("🧹 Old data deleted:")
        for item in removed:
            print(f"   - {item}")



# ============================================================
# VS CODE SPLIT TERMINALS (tasks.json)
# ============================================================

TASKS_JSON = r'''{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Rank: Desktop",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": ["desktop_rank.py"],
      "options": { "cwd": "${workspaceFolder}" },
      "presentation": {
        "reveal": "always",
        "panel": "dedicated",
        "group": "rank",
        "clear": true,
        "focus": false
      },
      "problemMatcher": []
    },
    {
      "label": "Rank: Mobile",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": ["mobile_rank.py"],
      "options": {
        "cwd": "${workspaceFolder}",
        "env": { "RANK_START_DELAY": "10" }
      },
      "presentation": {
        "reveal": "always",
        "panel": "dedicated",
        "group": "rank",
        "clear": true,
        "focus": false
      },
      "problemMatcher": []
    },
    {
      "label": "Rank: Combined Excel",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": ["run_both.py", "combine"],
      "options": { "cwd": "${workspaceFolder}" },
      "presentation": {
        "reveal": "always",
        "panel": "shared",
        "clear": false
      },
      "problemMatcher": []
    },
    {
      "label": "Rank: Desktop + Mobile (split terminals)",
      "dependsOn": ["Rank: Desktop", "Rank: Mobile"],
      "dependsOrder": "parallel",
      "problemMatcher": []
    },
    {
      "label": "Rank: ALL (split terminals + combined Excel)",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": ["run_both.py", "combine"],
      "dependsOn": ["Rank: Desktop", "Rank: Mobile"],
      "dependsOrder": "parallel",
      "options": { "cwd": "${workspaceFolder}" },
      "presentation": {
        "reveal": "always",
        "panel": "shared",
        "clear": false
      },
      "group": { "kind": "build", "isDefault": true },
      "problemMatcher": []
    }
  ]
}'''


def setup_vscode_tasks():

    """
    <folder>\\.vscode\\tasks.json is created here. A Python script cannot open VS Code terminals
    itself, but a VS Code task can: two tasks in the same 'group'
    -> do split terminals (left Desktop, right Mobile).
    """

    folder = os.path.join(BASE, ".vscode")

    os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, "tasks.json")

    status = "created"

    if os.path.exists(path):

        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()

        if existing.strip() == TASKS_JSON.strip():

            status = "already up to date"

        else:

            backup = path + ".bak"

            shutil.copyfile(path, backup)

            status = "updated (the old file is kept as tasks.json.bak)"

    if status != "already up to date":

        with open(path, "w", encoding="utf-8") as f:
            f.write(TASKS_JSON.strip() + "\n")

    print("=" * 70)
    print("🖥️📱 VS CODE SPLIT TERMINALS")
    print("=" * 70)
    print(f"✅ tasks.json {status}:")
    print(f"   {path}")
    print()
    print("NOTE: nothing has been started yet - this command only prepares the VS Code task.")
    print()
    print("Now do this in VS Code (the folder 'New Rank Automation' must be open):")
    print("   1) Press Ctrl+Shift+B   (or  Terminal > Run Task...)")
    print("   2) select 'Rank: ALL (split terminals + combined Excel)'")
    print()
    print("   -> DESKTOP runs in the left terminal and MOBILE in the right terminal, separately.")
    print("   -> When both finish, the combined Excel is built automatically.")
    print()
    print("For both in ONE terminal use:  python run_both.py together")


# ============================================================
# LAUNCH
# ============================================================

def script_path(name):

    return os.path.join(BASE, SCRIPTS[name])


def marker_path(name):

    return os.path.join(BASE, f".done_{name}")


def check_files(names):

    missing = [
        SCRIPTS[n] for n in names
        if not os.path.exists(script_path(n))
    ]

    if not os.path.exists(KEYWORDS_FILE):
        missing.append("keywords.txt")

    if missing:
        print("❌ These file(s) were not found in this folder:")
        for name in missing:
            print("   -", name)
        print(f"   Folder: {BASE}")
        return False

    return True


PRINT_LOCK = threading.Lock()


def safe_print(text):

    """Avoid crashing on characters the terminal encoding cannot represent."""

    with PRINT_LOCK:

        try:
            print(text, flush=True)

        except UnicodeEncodeError:

            encoding = sys.stdout.encoding or "utf-8"

            print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def pump_output(name, process):

    """Child script output in this terminal, with a [DESKTOP] / [MOBILE ] prefix."""

    prefix = f"[{name.upper():<7}] "

    try:
        for line in process.stdout:

            line = line.rstrip("\r\n")

            if line.strip():
                safe_print(prefix + line)

    except Exception:
        pass


def launch_in_terminal(name):

    """
    Runs the script in this same terminal (NO new cmd window).
    The output arrives through a pipe and pump_output() prints it with the prefix.
    """

    env = os.environ.copy()

    env["RANK_LAUNCHED"] = "1"

    env["RANK_DONE_FILE"] = marker_path(name)

    env["PYTHONIOENCODING"] = "utf-8"

    env["PYTHONUNBUFFERED"] = "1"

    try:
        os.remove(marker_path(name))
    except OSError:
        pass

    process = subprocess.Popen(
        [sys.executable, "-u", script_path(name)],
        cwd=BASE,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    reader = threading.Thread(
        target=pump_output,
        args=(name, process),
        daemon=True
    )

    reader.start()

    return process, reader


def remove_temp_files(names):

    """
    In combined mode only the combined Excel should remain:
    remove the intermediate live CSV files and .done markers (after the combined file is built).
    """

    paths = list(LIVE_CSV.values()) + [marker_path(n) for n in names]

    for path in paths:

        try:
            os.remove(path)
        except OSError:
            pass


def is_finished(name, process):

    return process.poll() is not None


def main():

    mode = (sys.argv[1].lower() if len(sys.argv) > 1 else "together")

    if mode == "together":
        mode = "both"

    if mode not in ("split", "setup", "both", "desktop", "mobile", "combine"):
        print("Use: python run_both.py [split|together|desktop|mobile|combine]")
        return

    # ---- split: prepare the VS Code task for two separate terminals ----
    if mode in ("split", "setup"):

        setup_vscode_tasks()

        return

    # ---- combine: only build the combined Excel -------------------
    if mode == "combine":

        print("=" * 70)
        print("📊 COMBINED EXCEL")
        print("=" * 70)

        if not os.path.exists(KEYWORDS_FILE):
            print("❌ keywords.txt was not found in this folder:", BASE)
            return

        saved = False

        for _ in range(5):

            if build_combined():
                saved = True
                break

            print("⚠️ Combined Excel was not saved (close it if it is open). Retrying...")

            time.sleep(5)

        if saved:
            print(f"✅ Combined Excel created: {COMBINED_FILE}")
        else:
            print("❌ The combined Excel could not be created.")

        return

    names = ["desktop", "mobile"] if mode == "both" else [mode]

    print("=" * 70)
    print(f"🚀 RANK AUTOMATION LAUNCHER  ({mode.upper()})")
    print("=" * 70)

    if not check_files(names):
        return

    # When running a single script, the other script may be running in another terminal,
    # so keep its fresh files; when running both together, clean everything.
    cleanup_old_data(protect_recent=(len(names) == 1))

    # ---- single: run in this same console -----------------------
    if len(names) == 1:

        subprocess.run([sys.executable, script_path(names[0])], cwd=BASE)

        return

    # ---- both: together, in this same terminal ---------------------
    processes = {}

    readers = []

    try:
        for position, name in enumerate(names):

            if position > 0:
                print(f"⏳ {name} starts in {STAGGER_SECONDS} sec...")
                time.sleep(STAGGER_SECONDS)

            print(f"▶️  Starting {name} ...")

            process, reader = launch_in_terminal(name)

            processes[name] = process

            readers.append(reader)

        print()
        print("✅ Both are running (separate Chrome browsers, output in this terminal).")
        print("   If a Google captcha/verification appears, solve it in that browser,")
        print("   the script checks by itself and continues. Press Ctrl+C to stop.")
        print()

        pending = dict(processes)

        last_refresh = 0

        while pending:

            for name in list(pending):

                if is_finished(name, pending[name]):

                    safe_print(f"🏁 {name} complete")

                    del pending[name]

            if time.time() - last_refresh >= REFRESH_SECONDS:

                build_combined()

                last_refresh = time.time()

            time.sleep(2)

    except KeyboardInterrupt:

        print()
        print("⛔ Ctrl+C: stopping both scripts...")

        for process in processes.values():

            try:
                process.wait(timeout=20)

            except Exception:

                try:
                    process.terminate()
                except Exception:
                    pass

    for reader in readers:
        reader.join(timeout=5)

    # final combined file (retry a few times if the Excel is open)
    saved = False

    for _ in range(5):

        if build_combined():
            saved = True
            break

        print("⚠️ Combined Excel was not saved (close it if it is open). Retrying...")

        time.sleep(5)

    print()
    print("=" * 70)
    print("✅ BOTH COMPLETE")
    print("=" * 70)

    if saved:
        remove_temp_files(names)
        print(f"📊 Combined Excel : {COMBINED_FILE}")
    else:
        print("❌ The combined Excel could not be created (the live CSV files are safe, you can try again).")

    print(f"📸 Screenshots    : {os.path.join(BASE, 'Screenshots')}")


if __name__ == "__main__":

    main()
