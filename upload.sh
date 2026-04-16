#!/bin/bash

BOT_TOKEN="8786141502:AAE_Zpl9G_V2bMC7wXhhwfGFcAW0nM4mVRM"
CHAT_ID="6155015997"

# ---------------- Telegram ----------------
send_telegram() {
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="${CHAT_ID}" \
        -d text="$1" \
        -d parse_mode="HTML" > /dev/null
}

# ---------------- Logging ----------------
log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

sep() {
    echo "--------------------------------------------------"
}

# ---------------- Link formatter ----------------
fmt_link() {
    local link="$1"
    if [[ -n "$link" && "$link" != "N/A" ]]; then
        echo "<a href=\"$link\">Download</a>"
    else
        echo "N/A"
    fi
}

# ---------------- Start ----------------
sep
log "ROM upload script started"
sep

PRODUCT_BASE="out/target/product"

log "Detecting device..."

DEVICE=$(find "$PRODUCT_BASE" -mindepth 1 -maxdepth 1 -type d \
    ! -name generic \
    ! -name obj \
    ! -name symbols \
    -printf "%f\n" | head -n 1)

PRODUCT_DIR="$PRODUCT_BASE/$DEVICE"

if [[ -z "$DEVICE" || ! -d "$PRODUCT_DIR" ]]; then
    log "ERROR: Device directory not detected"
    send_telegram "<b>❌ Build Failed</b>%0ADevice directory not detected!"
    exit 1
fi

log "Device detected: $DEVICE"

sep
log "Searching for ROM zip..."

ROM_ZIP=$(find "$PRODUCT_DIR" -type f -name "*${DEVICE}*.zip" \
    | grep -Ev "ota|symbol|target_files" \
    | sort -r \
    | head -n 1)

if [[ ! -f "$ROM_ZIP" ]]; then
    log "ERROR: ROM ZIP not found"
    send_telegram "<b>❌ Build Failed</b>%0AROM ZIP not found!"
    exit 1
fi

ZIP_NAME=$(basename "$ROM_ZIP")
log "ROM zip found: $ZIP_NAME"

# ---------------- ROM metadata ----------------
ROM_NAME=$(echo "$ZIP_NAME" | sed -E "s/-${DEVICE}.*//")

if echo "$ZIP_NAME" | grep -qi "UNOFFICIAL"; then
    BUILD_TYPE="Unofficial"
elif echo "$ZIP_NAME" | grep -qi "OFFICIAL"; then
    BUILD_TYPE="Official"
else
    BUILD_TYPE="Unknown"
fi

# ---------------- Images ----------------
BOOT_IMG="$PRODUCT_DIR/boot.img"
VENDOR_BOOT_IMG="$PRODUCT_DIR/vendor_boot.img"
DTBO_IMG="$PRODUCT_DIR/dtbo.img"

# ---------------- GoFile ----------------
log "Fetching GoFile server..."
SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name')

upload() {
    [[ -f "$1" ]] || { echo "N/A"; return; }

    curl -s -F "file=@$1" "https://${SERVER}.gofile.io/uploadFile" \
        | jq -r '.data.downloadPage' 2>/dev/null
}

sep
log "Uploading files to GoFile (parallel)..."

TMP_DIR=$(mktemp -d)

upload "$ROM_ZIP" > "$TMP_DIR/rom" &
upload "$BOOT_IMG" > "$TMP_DIR/boot" &
upload "$VENDOR_BOOT_IMG" > "$TMP_DIR/vendor_boot" &
upload "$DTBO_IMG" > "$TMP_DIR/dtbo" &

wait

ROM_LINK=$(cat "$TMP_DIR/rom")
BOOT_LINK=$(cat "$TMP_DIR/boot")
VENDOR_BOOT_LINK=$(cat "$TMP_DIR/vendor_boot")
DTBO_LINK=$(cat "$TMP_DIR/dtbo")

rm -rf "$TMP_DIR"

# ---------------- File info ----------------
SIZE=$(du -h "$ROM_ZIP" | awk '{print $1}')
MD5SUM=$(md5sum "$ROM_ZIP" | awk '{print $1}')

# ---------------- Telegram ----------------
sep
log "Sending Telegram message..."

send_telegram "📦 | <b>ROM compiled!!</b>

• <b>ROM</b>: ${ROM_NAME}
• <b>DEVICE</b>: ${DEVICE}
• <b>TYPE</b>: ${BUILD_TYPE}
• <b>SIZE</b>: ${SIZE}
• <b>MD5SUM</b>: <code>${MD5SUM}</code>
• <b>ROM</b>: $(fmt_link "$ROM_LINK")
• <b>BOOT</b>: $(fmt_link "$BOOT_LINK")
• <b>VENDOR_BOOT</b>: $(fmt_link "$VENDOR_BOOT_LINK")
• <b>DTBO</b>: $(fmt_link "$DTBO_LINK")
"

sep
log "Telegram notification sent"
log "Script finished"
sep
