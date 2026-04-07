#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
import requests
import re

YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
RED = "\033[31m"
CYAN = "\033[36m"

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

class CIBot:
    def __init__(self, config):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config['BOT_TOKEN']}"
        self.message_id = None

    def send_message(self, text):
        url = f"{self.base_url}/sendMessage"
        data = {"chat_id": self.config['CHAT_ID'], "text": text, "parse_mode": "html"}
        try:
            r = requests.post(url, data=data)
            res = r.json()
            if res.get("ok"): return res["result"]["message_id"]
        except: return None

    def edit_message(self, text):
        if not self.message_id: return
        url = f"{self.base_url}/editMessageText"
        data = {"chat_id": self.config['CHAT_ID'], "message_id": self.message_id, "text": text, "parse_mode": "html"}
        try: requests.post(url, data=data)
        except: pass

    def send_document(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                requests.post(f"{self.base_url}/sendDocument", data={"chat_id": self.config['CHAT_ID']}, files={"document": f})
        except: pass

def fetch_progress(log_file):
    try:
        if not os.path.exists(log_file): return None
        with open(log_file, "r") as f:
            lines = f.readlines()
            for line in reversed(lines[-20:]): 
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

    # Specific Configuration for LineageOS bp4a
    DEVICE = CONFIG.get('DEVICE', 'zephyr')
    RELEASE_TYPE = "bp4a"
    BUILD_VARIANT = "user"
    LUNCH_COMBO = f"lineage_{DEVICE}-{RELEASE_TYPE}-{BUILD_VARIANT}"

    print(f"\n{BOLD}{CYAN}# --- LineageOS CI Bot ---{RESET}")
    print(f"Target: {LUNCH_COMBO}")
    print(f"{BOLD_GREEN}1. m clean -> repo sync -> m bacon{RESET}")
    print(f"{BOLD_GREEN}2. repo sync -> m installclean -> m bacon{RESET}")
    print(f"{BOLD_GREEN}3. Dirty build (m bacon){RESET}")
    
    choice = input(f"\n{BOLD}Select option (1-3): {RESET}").strip()

    setup_env = f"source build/envsetup.sh && lunch {LUNCH_COMBO}"
    sync_cmd = "repo sync -j$(nproc --all) --no-tags --no-clone-bundle --current-branch --force-sync"
    build_cmd = "m bacon"
    
    if args.pick:
        build_cmd = f"repopick {' '.join(args.pick)} && m bacon"

    log_file = "build.log"
    if os.path.exists(log_file): os.remove(log_file)
    start_time = time.time()
    
    mode_map = {"1": "Clean", "2": "Installclean", "3": "Dirty"}
    mode_label = mode_map.get(choice, "Unknown")
    
    bot.message_id = bot.send_message(f"<b>Build Status: Starting</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>\n<b>Mode:</b> <code>{mode_label}</code>")

    if choice == '1':
        bot.edit_message(f"<b>Build Status: Cleaning...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>")
        subprocess.run(f"bash -c 'source build/envsetup.sh && m clean' | tee -a {log_file}", shell=True)
        
        bot.edit_message(f"<b>Build Status: Syncing Source...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>")
        subprocess.run(f"bash -c '{sync_cmd}' | tee -a {log_file}", shell=True)
        
        full_build_chain = f"{setup_env} && {build_cmd}"

    elif choice == '2':
        bot.edit_message(f"<b>Build Status: Syncing Source...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>")
        subprocess.run(f"bash -c '{sync_cmd}' | tee -a {log_file}", shell=True)
        
        full_build_chain = f"{setup_env} && m installclean && {build_cmd}"
    
    else:
        full_build_chain = f"{setup_env} && {build_cmd}"

    bot.edit_message(f"<b>Build Status: Compiling bacon...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>\n<b>Progress:</b> <code>Initializing</code>")
    
    compile_proc = subprocess.Popen(f"bash -c '{full_build_chain}' 2>&1 | tee -a {log_file}", shell=True)

    prev_prog = ""
    while compile_proc.poll() is None:
        curr_prog = fetch_progress(log_file)
        if curr_prog and curr_prog != prev_prog:
            bot.edit_message(f"<b>Build Status: Compiling</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>\n<b>Progress:</b> <code>{curr_prog}</code>")
            prev_prog = curr_prog
        time.sleep(30)

    out_dir = f"out/target/product/{DEVICE}"
    build_success = False
    rom_zip = None

    if os.path.exists(out_dir):
        zips = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".zip") and DEVICE in f and "ota" not in f.lower() and "target_files" not in f.lower()]
        if zips:
            rom_zip = max(zips, key=os.path.getmtime)
            if os.path.getmtime(rom_zip) > start_time:
                build_success = True

    if build_success:
        md5 = subprocess.check_output(f"md5sum {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
        size = subprocess.check_output(f"ls -sh {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
        
        bot.edit_message(
            f"<b>Build Status: Success ✅</b>\n\n"
            f"<b>Device:</b> <code>{DEVICE}</code>\n"
            f"<b>File:</b> <code>{os.path.basename(rom_zip)}</code>\n"
            f"<b>Size:</b> <code>{size}</code>\n"
            f"<b>MD5:</b> <code>{md5}</code>\n"
            f"<b>Duration:</b> <code>{format_duration(time.time()-start_time)}</code>"
        )
    else:
        bot.edit_message(f"<b>Build Status: Failed ❌</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>\nCheck build.log.")
        if os.path.exists(log_file):
            bot.send_document(log_file)

    if CONFIG.get('POWEROFF') == True:
        os.system("sudo poweroff")

if __name__ == "__main__":
    main()
        
