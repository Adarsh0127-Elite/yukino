#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
import requests
import re
import shutil
from datetime import datetime, timezone

# Visual Constants
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
RED = "\033[31m"
CYAN = "\033[36m"

ROOT_DIRECTORY = os.getcwd()

# Attempt to detect ROM name from directory
try:
    ROM_NAME = os.path.basename(ROOT_DIRECTORY)
except:
    ROM_NAME = "Unknown"

# Detect Android version from manifest
try:
    with open(".repo/manifests/default.xml", "r") as f:
        content = f.read()
        match = re.search(r'(?<=android-)[0-9]+', content)
        ANDROID_VERSION = match.group(0) if match else "Unknown"
except FileNotFoundError:
    ANDROID_VERSION = "Unknown"

# Config Loader
def load_env(file_path):
    config = {}
    if not os.path.exists(file_path):
        print(f"{RED}Error: Config file '{file_path}' not found.{RESET}")
        sys.exit(1)

    with open(file_path, 'r') as f:
        for line in f:
            if line.strip().startswith('#') or not line.strip(): continue
            if '=' in line:
                key, value = line.split('=', 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if value.lower() == 'true': value = True
                elif value.lower() == 'false': value = False
                config[key] = value
    return config

# Telegram Bot Class
class CIBot:
    def __init__(self, config):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config['BOT_TOKEN']}"
        self.message_id = None

    def send_message(self, text, chat_id=None):
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        url = f"{self.base_url}/sendMessage"
        data = {"chat_id": target_chat, "text": text, "parse_mode": "html", "disable_web_page_preview": True}
        try:
            r = requests.post(url, data=data)
            response = r.json()
            if response.get("ok"): return response["result"]["message_id"]
        except Exception as e: print(f"{RED}Telegram Error: {e}{RESET}")
        return None

    def edit_message(self, text, message_id=None, chat_id=None):
        msg_id = message_id if message_id else self.message_id
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        if not msg_id: return
        url = f"{self.base_url}/editMessageText"
        data = {"chat_id": target_chat, "message_id": msg_id, "text": text, "parse_mode": "html", "disable_web_page_preview": True}
        try: requests.post(url, data=data)
        except: pass

    def send_document(self, file_path, chat_id=None):
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        try:
            with open(file_path, 'rb') as f:
                requests.post(f"{self.base_url}/sendDocument", data={"chat_id": target_chat}, files={"document": f})
        except: pass

    def pin_message(self, message_id, chat_id=None):
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        if not message_id: return
        url = f"{self.base_url}/pinChatMessage"
        try:
            requests.post(url, data={"chat_id": target_chat, "message_id": message_id})
        except: pass

# Helper Functions
def upload_gofile(file_path):
    try:
        with open(file_path, 'rb') as f:
            r = requests.post('https://upload.gofile.io/uploadfile', files={'file': f})
        return r.json()['data']['downloadPage']
    except: return "Upload Failed"

def upload_rclone(file_path, remote, folder):
    try:
        subprocess.run(["rclone", "copy", file_path, f"{remote}:{folder}"], check=True)
        res = subprocess.run(["rclone", "link", f"{remote}:{folder}/{os.path.basename(file_path)}"], capture_output=True, text=True)
        return res.stdout.strip()
    except: return "Rclone Failed"

def fetch_progress(log_file):
    try:
        if not os.path.exists(log_file): return None
        with open(log_file, "r") as f:
            lines = f.readlines()
        for line in reversed(lines):
            match = re.search(r'(\d+%) (\d+/\d+)', line)
            if match: return f"{match.group(1)} ({match.group(2)})"
    except: pass
    return "Initializing..."

def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, default="config.env")
    parser.add_argument('-p', '--pick', nargs='+', help='Cherry-pick IDs')
    args = parser.parse_args()

    CONFIG = load_env(args.config)
    bot = CIBot(CONFIG)
    cpu_count = os.cpu_count()

    # Menu
    print(f"\n{BOLD}{CYAN}# --- BUILD MENU ---{RESET}")
    print(f"{BOLD_GREEN}1. m installclean{RESET} (Fast build, no sync)")
    print(f"{BOLD_GREEN}2. m clean + repo sync{RESET} (Full clean, fresh source)")
    print(f"{BOLD_GREEN}3. Plain Build{RESET} (No clean, no sync)")
    
    choice = input(f"\n{BOLD}Select option (1-3): {RESET}").strip()

    should_sync = False
    clean_cmd = ""

    if choice == '1':
        clean_cmd = "make installclean &&"
        print(f"{YELLOW}Mode: installclean{RESET}")
    elif choice == '2':
        clean_cmd = "make clean &&"
        should_sync = True
        print(f"{YELLOW}Mode: clean and resyncing{RESET}")
    elif choice == '3':
        clean_cmd = ""
        print(f"{YELLOW}Mode: Plain Build (No cleaning){RESET}")
    else:
        print(f"{RED}Invalid input. Exiting.{RESET}")
        sys.exit(1)

    # 1. Sync Section
    if should_sync:
        print(f"{BOLD_GREEN}Resyncing Sources...{RESET}")
        bot.message_id = bot.send_message(f"<b>Build Status: Resyncing Sources</b>\n<b>ROM:</b> {ROM_NAME}")
        start_sync = time.time()
        subprocess.run(f"repo sync -c -j{cpu_count} --force-sync --no-clone-bundle --no-tags", shell=True)
        bot.edit_message(f"<b>Sync Complete</b> in {format_duration(time.time()-start_sync)}")

    # 2. Preparation
    for f in ["out/error.log", "out/.lock", "build.log"]:
        if os.path.exists(f): os.remove(f)

    pick_cmd = f"repopick {' '.join(args.pick)} &&" if args.pick else ""
    
    now = datetime.now(timezone.utc)
    build_datetime = str(int(now.timestamp()))
    build_number = now.strftime("%Y%m%d00")
    export_vars = f"export BUILD_DATETIME={build_datetime} BUILD_NUMBER={build_number}"

    # 3. Build Section
    bot.message_id = bot.send_message(f"<b>Build Status: Compiling</b>\n<b>Device:</b> {CONFIG['DEVICE']}\n<b>Status:</b> Initializing...")
    start_build = time.time()

    full_cmd = (f"bash -c '{export_vars} && source build/envsetup.sh && "
                f"breakfast {CONFIG['DEVICE']} {CONFIG['VARIANT']} && "
                f"{clean_cmd} {pick_cmd} m evolution' 2>&1 | tee -a build.log")

    process = subprocess.Popen(full_cmd, shell=True)

    prev_prog = ""
    while process.poll() is None:
        curr_prog = fetch_progress("build.log")
        if curr_prog and curr_prog != prev_prog:
            bot.edit_message(f"<b>Build Status: Compiling</b>\n<b>ROM:</b> {ROM_NAME}\n<b>Progress:</b> <code>{curr_prog}</code>")
            prev_prog = curr_prog
        time.sleep(15)

    # 4. Result Logic
    build_success = False
    if os.path.exists("build.log"):
        with open("build.log", "r", encoding="utf-8", errors="ignore") as f:
            if "build completed successfully" in f.read().lower(): build_success = True

    out_dir = f"out/target/product/{CONFIG['DEVICE']}"
    if not build_success and os.path.exists(out_dir):
        if any(f.endswith(".zip") and CONFIG['DEVICE'] in f for f in os.listdir(out_dir)):
            build_success = True

    if not build_success:
        bot.edit_message("<b>Build Failed!</b>")
        if os.path.exists("out/error.log"): bot.send_document("out/error.log")
        sys.exit(1)

    # 5. Uploading (ROM ZIP ONLY)
    try:
        all_zips = [f for f in os.listdir(out_dir) if f.endswith(".zip") and CONFIG['DEVICE'] in f 
                    and "ota" not in f.lower() and "target_files" not in f.lower()]
        all_zips.sort(key=lambda x: os.path.getsize(os.path.join(out_dir, x)), reverse=True)
        rom_zip = os.path.join(out_dir, all_zips[0])

        print(f"{BOLD_GREEN}Uploading ROM Zip...{RESET}")
        r_remote = CONFIG.get('RCLONE_REMOTE')
        r_folder = CONFIG.get('RCLONE_FOLDER')
        rom_link = upload_rclone(rom_zip, r_remote, r_folder) if r_remote else upload_gofile(rom_zip)

        md5 = subprocess.check_output(f"md5sum {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
        size = subprocess.check_output(f"ls -sh {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()

        final_msg = (f"<b>Build Status: Success</b>\n\n"
                     f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
                     f"<b>Size:</b> <code>{size}</code>\n"
                     f"<b>MD5:</b> <code>{md5}</code>\n"
                     f"<b>Duration:</b> <code>{format_duration(time.time()-start_build)}</code>\n\n"
                     f"<b>Download:</b> <a href=\"{rom_link}\">ROM Zip</a>")
        
        bot.edit_message(final_msg)
        bot.pin_message(bot.message_id) # Pin restored here
        
    except Exception as e:
        bot.send_message(f"Upload failed: {e}")

    if CONFIG.get('POWEROFF'): os.system("sudo poweroff")

if __name__ == "__main__":
    main()
