#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
import requests
import re
import json

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

    def _get_keyboard(self):
        return json.dumps({
            "inline_keyboard": [[{"text": "🔄 Auto-Refreshing", "callback_data": "none"}]]
        })

    def send_message(self, text):
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": self.config['CHAT_ID'], 
            "text": text, 
            "parse_mode": "html",
            "reply_markup": self._get_keyboard()
        }
        try:
            r = requests.post(url, data=data)
            res = r.json()
            if res.get("ok"): 
                self.message_id = res["result"]["message_id"]
                return self.message_id
        except: return None

    def edit_message(self, text, show_button=True):
        if not self.message_id: 
            return self.send_message(text) # Fallback if ID is lost
        url = f"{self.base_url}/editMessageText"
        data = {
            "chat_id": self.config['CHAT_ID'], 
            "message_id": self.message_id, 
            "text": text, 
            "parse_mode": "html"
        }
        if show_button:
            data["reply_markup"] = self._get_keyboard()
            
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

    DEVICE = CONFIG.get('DEVICE', 'zephyr')
    LUNCH_COMBO = f"lineage_{DEVICE}-bp4a-user"

    print(f"\n{BOLD}{CYAN}# --- LineageOS CI Bot ---{RESET}")
    print(f"{BOLD_GREEN}1. Clean Build | 2. Installclean | 3. Dirty{RESET}")
    choice = input(f"\n{BOLD}Select option: {RESET}").strip()

    log_file = "build.log"
    if os.path.exists(log_file): os.remove(log_file)
    start_time = time.time()
    
    mode_label = {"1": "Clean", "2": "Installclean", "3": "Dirty"}.get(choice, "Unknown")
    
    # --- ONLY ONE SEND_MESSAGE CALL HERE ---
    bot.send_message(f"<b>Build Status: Initializing</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>\n<b>Mode:</b> <code>{mode_label}</code>")

    setup_env = f"source build/envsetup.sh && lunch {LUNCH_COMBO}"
    sync_cmd = "repo sync -j$(nproc --all) --no-tags --no-clone-bundle --current-branch --force-sync"
    build_cmd = "m bacon"
    if args.pick: build_cmd = f"repopick {' '.join(args.pick)} && m bacon"

    # Step 1: Clean/Sync (Updating the SAME message)
    if choice == '1':
        bot.edit_message(f"<b>Build Status: Cleaning...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>")
        subprocess.run(f"bash -c 'source build/envsetup.sh && m clean' >> {log_file} 2>&1", shell=True)
        
        bot.edit_message(f"<b>Build Status: Syncing...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>")
        subprocess.run(f"bash -c '{sync_cmd}' >> {log_file} 2>&1", shell=True)
        full_build_chain = f"{setup_env} && {build_cmd}"
    elif choice == '2':
        bot.edit_message(f"<b>Build Status: Syncing...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>")
        subprocess.run(f"bash -c '{sync_cmd}' >> {log_file} 2>&1", shell=True)
        full_build_chain = f"{setup_env} && m installclean && {build_cmd}"
    else:
        full_build_chain = f"{setup_env} && {build_cmd}"

    # Step 2: Compiling
    bot.edit_message(f"<b>Build Status: Compiling...</b>\n<b>Target:</b> <code>{LUNCH_COMBO}</code>\n<b>Progress:</b> <code>Starting</code>")
    compile_proc = subprocess.Popen(f"bash -c '{full_build_chain}' 2>&1 | tee -a {log_file}", shell=True)

    while compile_proc.poll() is None:
        curr_prog = fetch_progress(log_file)
        elapsed = format_duration(time.time() - start_time)
        bot.edit_message(
            f"<b>Build Status: Compiling</b>\n"
            f"<b>Target:</b> <code>{LUNCH_COMBO}</code>\n"
            f"<b>Progress:</b> <code>{curr_prog or 'Running...'}</code>\n"
            f"<b>Elapsed:</b> <code>{elapsed}</code>"
        )
        time.sleep(30)

    # Final Result
    total_duration = format_duration(time.time() - start_time)
    out_dir = f"out/target/product/{DEVICE}"
    rom_zip = None

    if os.path.exists(out_dir):
        zips = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".zip") and DEVICE in f and "ota" not in f.lower()]
        if zips:
            rom_zip = max(zips, key=os.path.getmtime)
            if os.path.getmtime(rom_zip) > start_time:
                # Success
                size = subprocess.check_output(f"ls -sh {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
                bot.edit_message(
                    f"<b>Build Status: Success ✅</b>\n\n"
                    f"<b>File:</b> <code>{os.path.basename(rom_zip)}</code>\n"
                    f"<b>Size:</b> <code>{size}</code>\n"
                    f"<b>Duration:</b> <code>{total_duration}</code>",
                    show_button=False
                )
                return

    # Failure
    bot.edit_message(f"<b>Build Status: Failed ❌</b>\n<b>Elapsed:</b> <code>{total_duration}</code>", show_button=False)
    if os.path.exists(log_file): bot.send_document(log_file)

    if CONFIG.get('POWEROFF') == True: os.system("sudo poweroff")

if __name__ == "__main__":
    main()
