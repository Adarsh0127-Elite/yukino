#!/bin/bash

# ================= Configuration =================
# Telegram credentials
BOT_TOKEN="8786141502:AAE_Zpl9G_V2bMC7wXhhwfGFcAW0nM4mVRM"
CHAT_ID="6155015997"

# Build Details
USER_NAME="Adarsh"

# ================= Internal Config =================
PRODUCT_BASE="out/target/product"
TMP_DIR=$(mktemp -d)

# ================= Telegram Functions =================
escape_html() {
    local text="$1"
    echo "$text" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g'
}

send_telegram_text() {
    local text="$1"
    local reply_markup="$2"

    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${CHAT_ID}" \
        -d text="${text}" \
        -d reply_markup="${reply_markup}" \
        -d parse_mode="HTML" > /dev/null
}

generate_buttons() {
    local rom_label=$(escape_html "${ZIP_NAME} ($ROM_SIZE)")
    local boot_label=$(escape_html "boot.img ($BOOT_SIZE)")
    local vendor_boot_label=$(escape_html "vendor_boot.img ($VENDOR_BOOT_SIZE)")
    local dtbo_label=$(escape_html "dtbo.img ($DTBO_SIZE)")

    local markup=$(cat <<EOF
{
  "inline_keyboard": [
    [
      { "text": "${boot_label}", "url": "${BOOT_LINK}" },
      { "text": "${vendor_boot_label}", "url": "${VENDOR_BOOT_LINK}" }
    ],
    [
      { "text": "${dtbo_label}", "url": "${DTBO_LINK}" }
    ],
    [
      { "text": "${rom_label}", "url": "${ROM_LINK}" }
    ]
  ]
}
EOF
)
    echo "$markup"
}

# ================= Logging =================
log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

# ================= Device Detection =================
log "--------------------------------------------------"
log "Detecting device and files..."

DEVICE=$(find "$PRODUCT_BASE" -mindepth 1 -maxdepth 1 -type d \
    ! -name generic ! -name obj ! -name symbols \
    -printf "%f\n" | head -n 1)

PRODUCT_DIR="$PRODUCT_BASE/$DEVICE"

if [[ -z "$DEVICE" || ! -d "$PRODUCT_DIR" ]]; then
    log "ERROR: Device directory not detected"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${CHAT_ID}" \
        -d text="❌ <b>Build Upload Failed</b>%0ADevice directory not detected." \
        -d parse_mode="HTML" > /dev/null
    exit 1
fi

log "Device: $DEVICE"

ROM_ZIP=$(find "$PRODUCT_DIR" -type f -name "*${DEVICE}*.zip" \
    | grep -Ev "ota|symbol|target_files" \
    | sort -r \
    | head -n 1)

if [[ ! -f "$ROM_ZIP" ]]; then
    log "ERROR: ROM ZIP not found"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${CHAT_ID}" \
        -d text="❌ <b>Build Upload Failed</b>%0AROM ZIP not found." \
        -d parse_mode="HTML" > /dev/null
    exit 1
fi

# ================= Image Detection =================
BOOT_IMG="$PRODUCT_DIR/boot.img"
VENDOR_BOOT_IMG="$PRODUCT_DIR/vendor_boot.img"
DTBO_IMG="$PRODUCT_DIR/dtbo.img"

if [[ ! -f "$BOOT_IMG" ]]; then BOOT_IMG="N/A"; fi
if [[ ! -f "$VENDOR_BOOT_IMG" ]]; then VENDOR_BOOT_IMG="N/A"; fi
if [[ ! -f "$DTBO_IMG" ]]; then DTBO_IMG="N/A"; fi

# ================= GoFile Upload Logic =================
log "--------------------------------------------------"
log "Uploading artifacts to GoFile (parallel)..."

upload() {
    [[ "$1" == "N/A" ]] && { echo "N/A"; return; }
    [[ -f "$1" ]] || { echo "N/A"; return; }

    SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name')
    curl -s -F "file=@$1" "https://${SERVER}.gofile.io/uploadFile" \
        | jq -r '.data.downloadPage' 2>/dev/null
}

upload "$ROM_ZIP" > "$TMP_DIR/rom" &
upload "$BOOT_IMG" > "$TMP_DIR/boot" &
upload "$VENDOR_BOOT_IMG" > "$TMP_DIR/vendor_boot" &
upload "$DTBO_IMG" > "$TMP_DIR/dtbo" &

wait

ROM_LINK=$(cat "$TMP_DIR/rom")
BOOT_LINK=$(cat "$TMP_DIR/boot")
VENDOR_BOOT_LINK=$(cat "$TMP_DIR/vendor_boot")
DTBO_LINK=$(cat "$TMP_DIR/dtbo")

if [[ -z "$ROM_LINK" ]]; then ROM_LINK="N/A"; fi
if [[ -z "$BOOT_LINK" ]]; then BOOT_LINK="N/A"; fi
if [[ -z "$VENDOR_BOOT_LINK" ]]; then VENDOR_BOOT_LINK="N/A"; fi
if [[ -z "$DTBO_LINK" ]]; then DTBO_LINK="N/A"; fi

rm -rf "$TMP_DIR"

# ================= File Info Calculation =================
log "Calculating hashes and sizes..."

fmt_size() {
    du -h "$1" | awk '{print $1}'
}

ROM_SIZE=$(fmt_size "$ROM_ZIP")
BOOT_SIZE=$(fmt_size "$BOOT_IMG")
VENDOR_BOOT_SIZE=$(fmt_size "$VENDOR_BOOT_IMG")
DTBO_SIZE=$(fmt_size "$DTBO_IMG")

ROM_SHA256=$(sha256sum "$ROM_ZIP" | awk '{print $1}')
BOOT_SHA256=$(sha256sum "$BOOT_IMG" | awk '{print $1}' 2>/dev/null || echo "N/A")
VENDOR_BOOT_SHA256=$(sha256sum "$VENDOR_BOOT_IMG" | awk '{print $1}' 2>/dev/null || echo "N/A")
DTBO_SHA256=$(sha256sum "$DTBO_IMG" | awk '{print $1}' 2>/dev/null || echo "N/A")

ZIP_NAME=$(basename "$ROM_ZIP")

# ================= Time & Duration Integration =================
# Grabs the exported variables from the parent CI script.
# If they are empty/missing, it falls back to "Unknown" to prevent UI breakage.
FINAL_START_TIME="${START_TIME_STR:-"Unknown"}"
FINAL_DURATION="${DURATION_STR:-"Unknown"}"

# ================= Telegram UI Construction =================
log "--------------------------------------------------"
log "Sending UI notification..."

MESSAGE_TEXT=$(cat <<EOF
✅ <b>Build Completed on ${DEVICE}</b>

<b>User:</b> ${USER_NAME}
<b>Started:</b> ${FINAL_START_TIME}
<b>Duration:</b> ${FINAL_DURATION}

🎉 <b>Build Artifact(s) Uploaded:</b>
1. <b>File:</b> <code>${ZIP_NAME}</code>
   <b>Type:</b> ZIP | <b>Size:</b> ${ROM_SIZE}
   <b>SHA256:</b>
<code>${ROM_SHA256}</code>
2. <b>File:</b> <code>boot.img</code>
   <b>Type:</b> IMG | <b>Size:</b> ${BOOT_SIZE}
   <b>SHA256:</b>
<code>${BOOT_SHA256}</code>
3. <b>File:</b> <code>vendor_boot.img</code>
   <b>Type:</b> IMG | <b>Size:</b> ${VENDOR_BOOT_SIZE}
   <b>SHA256:</b>
<code>${VENDOR_BOOT_SHA256}</code>
4. <b>File:</b> <code>dtbo.img</code>
   <b>Type:</b> IMG | <b>Size:</b> ${DTBO_SIZE}
   <b>SHA256:</b>
<code>${DTBO_SHA256}</code>
EOF
)

REPLY_MARKUP_JSON=$(generate_buttons)

send_telegram_text "$MESSAGE_TEXT" "$REPLY_MARKUP_JSON"

log "UI notification sent."
log "--------------------------------------------------"
log "Script finished."
