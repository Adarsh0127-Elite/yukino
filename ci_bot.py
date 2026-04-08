#!/usr/bin/env python3
import os
import sys
import time
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
        return config
    with open(file_path, 'r') as f:
        for line in f:
            if line.strip().startswith('#') or not line.strip(): continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.split('#')[0].strip().strip('"').strip("'")
    return config

def get_env_info(var_name, fallback="Unknown"):
    """Pulls info directly from the server's shell environment."""
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

def render_advanced_bar(percentage):
    total_slots = 15
    filled_slots = int((total_slots * percentage) // 100)
    bar = '█' * filled_slots + '▒' * (total_slots - filled_slots)
    return f"[{bar}]"

def fetch_stats(log_file, start_time):
    stats = {"percentage": 0.0, "done": 0, "total": 0, "tasks": "0", "eta": "Calculating..."}
    try:
        if not os.path.exists(log_file): return stats
        with open(log_file, "r") as f:
            content = f.read()
            # Match progress like [ 12% 1234/10000]
            matches = re.findall(r'\[\s*(\d+)%\s+(\d+)/(\d+)\]', content)
            if matches:
                last = matches[-1]
                stats["percentage"], stats["done"], stats["total"] = float(last[0]), int(last[1]), int(last[2])
                if stats["percentage"] > 0:
                    elapsed = time.time() - start_time
                    total_est = (elapsed * 100) / stats["percentage"]
                    remaining = total_est - elapsed
                    stats["eta"] = f"{int(remaining // 60)}m {int(remaining % 60)}s"
            
            task_match = re.findall(r'(\d+) tasks running', content)
            if task_match: stats["tasks"] = task_match[-1]
    except: pass
    return stats

def main():
    # Setup config
    CONFIG = load_env(os.path.expanduser("~/lunaris/config.env"))
    bot = CIBot(CONFIG)
    log_file = "build.log"
    
    # --- DYNAMIC SERVER CONFIG EXTRACTION ---
    # Scrape variables set by 'lunch' or environment
    DEVICE = get_env_info('TARGET_DEVICE', 'lisaa')
    VARIANT = get_env_info('TARGET_BUILD_VARIANT', 'user')
    RELEASE = get_env_info('TARGET_RELEASE', 'ap2a')
    
    # Android Version Fix (Checks for A16 specifically)
    ANDROID_VER = get_env_info('PLATFORM_VERSION', '16')
    
    # ROM Name Detection (Scrapes 'TARGET_PRODUCT' or env)
    # If TARGET_PRODUCT is 'lunaris_lisaa-user', it detects LunarisAOSP
    TARGET_PROD = get_env_info('TARGET_PRODUCT', 'lunaris_lisaa')
    ROM = "LunarisAOSP" if "lunaris" in TARGET_PROD.lower() else get_env_info('ROM_NAME', 'LunarisAOSP')
    
    # GMS Detection
    GMS_ENV = get_env_info('WITH_GMS', 'false').lower()
    GMS = str(CONFIG.get('WITH_GMS', GMS_ENV))

    print(f"\n{BOLD}{CYAN}# --- Build Started: {ROM} (Android {ANDROID_VER}) ---{RESET}")
    
    if os.path.exists(log_file): os.remove(log_file)
    start_time = time.time()
    
    # Execution
    # Note: No 'source' or 'lunch' here, we assume you already did that in the shell.
    compile_proc = subprocess.Popen(f"bash -c 'm bacon' 2>&1 | tee {log_file}", shell=True)

    bot.edit_message(f"<b>⚙️ Build Initialization</b>\n<b>ROM:</b> {ROM}\n<b>Device:</b> {DEVICE}\n<b>Android:</b> {ANDROID_VER}")

    while compile_proc.poll() is None:
        s = fetch_stats(log_file, start_time)
        elapsed_raw = time.time() - start_time
        elapsed = f"{int(elapsed_raw // 60)}m {int(elapsed_raw % 60)}s"
        
        msg = (
            f"<b>⚙️ Build In Progress ({s['tasks']} tasks)</b> for <b>{ROM} on {DEVICE}</b>\n"
            f"👤 User: {os.getlogin()}\n"
            f"📊 Progress: <code>{render_advanced_bar(s['percentage'])}</code> {s['percentage']}%\n"
            f"<b>Actions:</b> <code>{s['done']}/{s['total']}</code>\n"
            f"⏳ <b>Elapsed:</b> <code>{elapsed}</code>\n"
            f"🕒 <b>ETA:</b> <code>{s['eta']}</code>\n\n"
            f"<b>🔧 Configuration:</b>\n"
            f"<b>Variant:</b> <code>{VARIANT}</code>\n"
            f"<b>Android Version:</b> <code>{ANDROID_VER}</code>\n"
            f"<b>Release:</b> <code>{RELEASE}</code>\n"
            f"<b>GMS:</b> <code>{GMS}</code>\n\n"
            f"<i>My code is compiling, so I must be working... right?</i> 💻"
        )
        bot.edit_message(msg)
        time.sleep(30)

    # Final Result
    duration = f"{int((time.time() - start_time) // 60)}m {int((time.time() - start_time) % 60)}s"
    if compile_proc.returncode == 0:
        bot.edit_message(f"<b>✅ Build Successful</b>\n<b>ROM:</b> {ROM}\n<b>Time:</b> {duration}", show_button=False)
    else:
        bot.edit_message(f"<b>❌ Build Failed</b>\n<b>ROM:</b> {ROM}\n<b>Time:</b> {duration}", show_button=False)

if __name__ == "__main__":
    main()
