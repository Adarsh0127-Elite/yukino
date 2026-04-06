#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
import requests
import re
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
    return None

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

    # Menu
    print(f"\n{BOLD}{CYAN}# --- Build Menu ---{RESET}")
    print(f"{BOLD_GREEN}1. m installclean + sync{RESET}")
    print(f"{BOLD_GREEN}2. m clean + sync{RESET}")
    print(f"{BOLD_GREEN}3. Plain Build{RESET}")
    
    choice = input(f"\n{BOLD}Select option (1-3): {RESET}").strip()

    # Build Command List
    cmd_list = [f"source build/envsetup.sh", f"breakfast {CONFIG['DEVICE']} {CONFIG['VARIANT']}"]

    if choice == '1':
        cmd_list.append("repo sync -c -j$(nproc --all) --force-sync --no-clone-bundle --no-tags")
        cmd_list.append("make installclean")
    elif choice == '2':
        cmd_list.append("repo sync -c -j$(nproc --all) --force-sync --no-clone-bundle --no-tags")
        cmd_list.append("make clean")
    
    if args.pick:
        cmd_list.append(f"repopick {' '.join(args.pick)}")

    # ALWAYS add evolution command at the end of the chain
    cmd_list.append("m evolution")

    # Combine with && to ensure one failure stops the whole process
    full_cmd_chain = " && ".join(cmd_list)

    # Preparation
    if os.path.exists("build.log"): os.remove("build.log")
    start_time_stamp = time.time() # Used to verify if ZIP is actually new

    bot.message_id = bot.send_message(f"<b>Build Status: Starting</b>\n<b>ROM:</b> {ROM_NAME}\n<b>Device:</b> {CONFIG['DEVICE']}")

    # Start Build
    full_cmd = f"bash -c '{full_cmd_chain}' 2>&1 | tee build.log"
    process = subprocess.Popen(full_cmd, shell=True)

    prev_prog = ""
    while process.poll() is None:
        curr_prog = fetch_progress("build.log")
        if curr_prog and curr_prog != prev_prog:
            bot.edit_message(f"<b>Build Status: Compiling</b>\n<b>ROM:</b> {ROM_NAME}\n<b>Progress:</b> <code>{curr_prog}</code>")
            prev_prog = curr_prog
        time.sleep(30)

    # Result Verification
    out_dir = f"out/target/product/{CONFIG['DEVICE']}"
    build_success = False
    rom_zip = None

    if os.path.exists(out_dir):
        # Find all zips, excluding ota/target files
        all_zips = [os.path.join(out_dir, f) for f in os.listdir(out_dir) 
                    if f.endswith(".zip") and CONFIG['DEVICE'] in f 
                    and "ota" not in f.lower() and "target_files" not in f.lower()]
        
        if all_zips:
            # Get the most recently modified zip
            latest_zip = max(all_zips, key=os.path.getmtime)
            # CHECK: Was this file created AFTER we started the script?
            if os.path.getmtime(latest_zip) > start_time_stamp:
                build_success = True
                rom_zip = latest_zip

    if build_success:
        bot.edit_message("<b>Build Successful!</b> Uploading...")
        
        r_remote = CONFIG.get('RCLONE_REMOTE')
        r_folder = CONFIG.get('RCLONE_FOLDER')
        rom_link = upload_rclone(rom_zip, r_remote, r_folder)

        md5 = subprocess.check_output(f"md5sum {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
        size = subprocess.check_output(f"ls -sh {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()

        final_msg = (f"<b>Build Status: Success ✅</b>\n\n"
                     f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
                     f"<b>Size:</b> <code>{size}</code>\n"
                     f"<b>MD5:</b> <code>{md5}</code>\n"
                     f"<b>Duration:</b> <code>{format_duration(time.time()-start_time_stamp)}</code>\n\n"
                     f"<b>Download:</b> <a href=\"{rom_link}\">ROM Zip</a>")
        
        bot.edit_message(final_msg)
        bot.pin_message(bot.message_id)
    else:
        bot.edit_message(f"<b>Build Failed! ❌</b>\nROM zip not found or compilation error.")
        if os.path.exists("out/error.log"): bot.send_document("out/error.log")

    if CONFIG.get('POWEROFF') == True: os.system("sudo poweroff")

if __name__ == "__main__":
    main()
