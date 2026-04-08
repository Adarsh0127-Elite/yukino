#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import requests
import re
import json
from datetime import datetime

# Terminal Colors
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
RED = "\033[31m"
CYAN = "\033[36m"

def load_env(file_path):
    config = {}
    if not os.path.exists(file_path): return config
    with open(file_path, 'r') as f:
        for line in f:
            if line.strip().startswith('#') or not line.strip(): continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.split('#')[0].strip().strip('"').strip("'")
    return config

def get_env_info(var_name, fallback="Unknown"):
    return os.environ.get(var_name, fallback)

class CIBot:
    def __init__(self, config):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config['BOT_TOKEN']}"
        self.message_id = None

    def edit_message(self, text, show_button=True):
        url = f"{self.base_url}/{'sendMessage' if not self.message_id else 'editMessageText'}"
        data = {"chat_id": self.config['CHAT_ID'], "text": text, "parse_mode": "html"}
        if self.message_id: data["message_id"] = self.message_id
        if show_button:
            data["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": "🔄 Building Lunaris...", "callback_data": "none"}]]})
        
        try:
            r = requests.post(url, data=data).json()
            if not self.message_id and r.get("ok"): self.message_id = r["result"]["message_id"]
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

def fetch_stats(log_file, start_time):
    stats = {"percentage": 0.0, "done": 0, "total": 0, "tasks": "0", "eta": "0m 0s"}
    try:
        if not os.path.exists(log_file): return stats
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Search reversed to find the most recent build progress
            for line in reversed(lines[-50:]):
                match = re.search(r'\[\s*(\d+)%\s+(\d+)/(\d+)\]', line)
                if match:
                    stats["percentage"] = float(match.group(1))
                    stats["done"] = int(match.group(2))
                    stats["total"] = int(match.group(3))
                    
                    if stats["percentage"] > 0:
                        elapsed = time.time() - start_time
                        total_est = (elapsed * 100) / stats["percentage"]
                        remaining = total_est - elapsed
                        stats["eta"] = f"{int(remaining // 60)}m {int(remaining % 60)}s"
                    break
            
            for line in reversed(lines[-20:]):
                task_match = re.search(r'(\d+) tasks running', line)
                if task_match:
                    stats["tasks"] = task_match.group(1)
                    break
    except: pass
    return stats

def format_duration_long(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    parts = []
    if h > 0: parts.append(f"{h} hour{'s' if h > 1 else ''}")
    if m > 0: parts.append(f"{m} minute{'s' if m > 1 else ''}")
    if s > 0: parts.append(f"{s} second{'s' if s > 1 else ''}")
    return ", ".join(parts) if parts else "0 seconds"

def main():
    CONFIG = load_env(os.path.expanduser("~/lunaris/config.env"))
    bot = CIBot(CONFIG)
    log_file = "build.log"
    
    # Environment Detection
    DEVICE = get_env_info('TARGET_DEVICE', 'lisaa')
    VARIANT = get_env_info('TARGET_BUILD_VARIANT', 'user')
    RELEASE = get_env_info('TARGET_RELEASE', 'bp4a')
    ANDROID_VER = get_env_info('PLATFORM_VERSION', '16')
    USER_NAME = os.getlogin()
    ROM = "LunarisAOSP"
    GMS = str(get_env_info('WITH_GMS', 'false')).lower()

    start_time_unix = time.time()
    start_time_fmt = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p UTC+05:30")

    if os.path.exists(log_file): os.remove(log_file)
    compile_proc = subprocess.Popen(f"bash -c 'm bacon' 2>&1 | tee {log_file}", shell=True)

    while compile_proc.poll() is None:
        s = fetch_stats(log_file, start_time_unix)
        elapsed_raw = time.time() - start_time_unix
        em, es = divmod(int(elapsed_raw), 60)
        
        msg = (
            f"⚙️ <b>Build In Progress ({s['tasks']} tasks)</b> for <b>{ROM} on {DEVICE}</b>\n"
            f"👤 User: {USER_NAME}\n"
            f"📊 Progress: <code>{render_advanced_bar(s['percentage'])}</code>\n"
            f"{s['percentage']}%\n"
            f"Actions: {s['done']}/{s['total']}\n"
            f"⌛ Elapsed: {em}m {es}s\n"
            f"⌚ ETA: {s['eta']}\n\n"
            f"🔧 <b>Configuration:</b>\n"
            f"Variant: <code>{VARIANT}</code>\n"
            f"Android Version: <code>{ANDROID_VER}</code>\n"
            f"Release: <code>{RELEASE}</code>\n"
            f"GMS: <code>{GMS}</code>\n\n"
            f"<i>My code is compiling, so I must be working... right?</i> 💻"
        )
        bot.edit_message(msg)
        time.sleep(30)

    # Final Result
    final_stats = fetch_stats(log_file, start_time_unix)
    duration = format_duration_long(time.time() - start_time_unix)
    
    if compile_proc.returncode == 0:
        success_msg = (
            f"✅ <b>Build Successful for {ROM} on {DEVICE}</b>\n"
            f"<b>Duration:</b> {duration}\n"
            f"<b>Android:</b> {ANDROID_VER}"
        )
        bot.edit_message(success_msg, show_button=False)
    else:
        fail_msg = (
            f"❌ <b>Build Failed for {ROM} on {DEVICE}</b>\n"
            f"<b>User:</b> {USER_NAME}\n"
            f"<b>Started:</b> {start_time_fmt}\n"
            f"<b>Duration:</b> {duration}\n"
            f"📊 <b>Build Stats:</b> {final_stats['done']}/{final_stats['total']} actions (1 failed)\n"
            f"🔧 <b>Configuration:</b>\n"
            f"  • Variant: <code>{VARIANT}</code>\n"
            f"  • Type: release\n"
            f"  • Release: <code>{RELEASE}</code>\n"
            f"  • GMS: <code>{GMS}</code>\n\n"
            f"📄 Check logs for details. Error log uploaded if available."
        )
        bot.edit_message(fail_msg, show_button=False)
        if os.path.exists(log_file):
            bot.send_document(log_file)

    if CONFIG.get('POWEROFF') == 'true':
        os.system("sudo poweroff")

if __name__ == "__main__":
    main()
