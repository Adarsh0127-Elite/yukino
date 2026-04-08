#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
import requests
import re
import json

# Terminal Colors
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

    def _get_keyboard(self, status="running"):
        if status == "running":
            return json.dumps({"inline_keyboard": [[{"text": "🔄 Building...", "callback_data": "none"}]]})
        return None

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
        if not self.message_id: return self.send_message(text)
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

def render_advanced_bar(percentage):
    total_slots = 15
    filled_slots = int((total_slots * percentage) // 100)
    bar = '█' * filled_slots + '▒' * (total_slots - filled_slots)
    return f"[{bar}]"

def fetch_advanced_stats(log_file, start_time):
    stats = {"percentage": 0.0, "done": 0, "total": 0, "eta": "Calculating...", "tasks": "Checking"}
    try:
        if not os.path.exists(log_file): return stats
        with open(log_file, "r") as f:
            content = f.read()
            # Match progress like [ 12% 1234/10000]
            matches = re.findall(r'\[\s*(\d+)%\s+(\d+)/(\d+)\]', content)
            if matches:
                last = matches[-1]
                stats["percentage"] = float(last[0])
                stats["done"] = int(last[1])
                stats["total"] = int(last[2])
                
                if stats["percentage"] > 0:
                    elapsed = time.time() - start_time
                    total_est = (elapsed * 100) / stats["percentage"]
                    stats["eta"] = format_duration(total_est - elapsed)
            
            # Match tasks running
            task_match = re.findall(r'(\d+) tasks running', content)
            if task_match: stats["tasks"] = task_match[-1]
    except Exception: pass # Fixed the syntax error here
    return stats

def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 0: return "Finishing..."
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m {s}s"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, default="config.env")
    parser.add_argument('-p', '--pick', nargs='+', help='Cherry-pick IDs')
    args = parser.parse_args()

    CONFIG = load_env(args.config)
    bot = CIBot(CONFIG)

    DEVICE = CONFIG.get('DEVICE', 'zephyr')
    VARIANT = CONFIG.get('BUILD_VARIANT', 'user')
    TYPE = CONFIG.get('RELEASE_TYPE', 'bp4a')
    GMS = CONFIG.get('WITH_GMS', True)
    LUNCH_COMBO = f"lineage_{DEVICE}-{TYPE}-{VARIANT}"

    print(f"\n{BOLD}{CYAN}# --- AxionOS CI Bot ---{RESET}")
    choice = input(f"{BOLD_GREEN}1. Clean | 2. Installclean | 3. Dirty{RESET}\nChoice: ").strip()

    log_file = "build.log"
    if os.path.exists(log_file): os.remove(log_file)
    start_time = time.time()
    
    bot.send_message(f"<b>⚙️ Build Initialization</b>\n<b>ROM:</b> AxionOS for {DEVICE}\n<b>Target:</b> {LUNCH_COMBO}")

    setup_env = f"source build/envsetup.sh && lunch {LUNCH_COMBO}"
    sync_cmd = "repo sync -j$(nproc --all) --no-tags --no-clone-bundle --current-branch --force-sync"
    build_cmd = "m bacon"
    if args.pick: build_cmd = f"repopick {' '.join(args.pick)} && m bacon"

    # Pre-build logic
    if choice == '1':
        bot.edit_message("<b>⚙️ Status:</b> Cleaning and Syncing...")
        subprocess.run(f"bash -c 'source build/envsetup.sh && m clean && {sync_cmd}' >> {log_file} 2>&1", shell=True)
    elif choice == '2':
        bot.edit_message("<b>⚙️ Status:</b> Syncing Source...")
        subprocess.run(f"bash -c '{sync_cmd}' >> {log_file} 2>&1", shell=True)
        setup_env += " && m installclean"

    # Compile
    compile_proc = subprocess.Popen(f"bash -c '{setup_env} && {build_cmd}' 2>&1 | tee -a {log_file}", shell=True)

    while compile_proc.poll() is None:
        s = fetch_advanced_stats(log_file, start_time)
        elapsed = format_duration(time.time() - start_time)
        
        msg = (
            f"<b>⚙️ Build In Progress ({s['tasks']} tasks)</b> for <b>AxionOS on {DEVICE}</b>\n"
            f"👤 User: {os.getlogin()}\n"
            f"📊 Progress: <code>{render_advanced_bar(s['percentage'])}</code> {s['percentage']}%\n"
            f"<b>Actions:</b> <code>{s['done']}/{s['total']}</code>\n"
            f"⏳ <b>Elapsed:</b> <code>{elapsed}</code>\n"
            f"🕒 <b>ETA:</b> <code>{s['eta']}</code>\n\n"
            f"<b>🔧 Configuration:</b>\n"
            f"<b>Variant:</b> <code>{VARIANT}</code> | <b>Type:</b> <code>{TYPE}</code>\n"
            f"<b>GMS:</b> <code>{str(GMS).lower()}</code>\n\n"
            f"<i>My code is compiling, so I must be working... right?</i> 💻"
        )
        bot.edit_message(msg)
        time.sleep(30)

    # Final logic
    duration = format_duration(time.time() - start_time)
    out_dir = f"out/target/product/{DEVICE}"
    rom_zip = None

    if os.path.exists(out_dir):
        zips = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".zip") and DEVICE in f and "ota" not in f.lower()]
        if zips:
            rom_zip = max(zips, key=os.path.getmtime)
            if os.path.getmtime(rom_zip) > start_time:
                size = subprocess.check_output(f"ls -sh {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
                bot.edit_message(f"<b>✅ Build Successful</b>\n\n<b>File:</b> <code>{os.path.basename(rom_zip)}</code>\n<b>Size:</b> <code>{size}</code>\n<b>Time:</b> <code>{duration}</code>", show_button=False)
                if CONFIG.get('POWEROFF'): os.system("sudo poweroff")
                return

    bot.edit_message(f"<b>❌ Build Failed</b>\n<b>Time:</b> <code>{duration}</code>\nCheck build.log below.", show_button=False)
    bot.send_document(log_file)
    if CONFIG.get('POWEROFF'): os.system("sudo poweroff")

if __name__ == "__main__":
    main()
