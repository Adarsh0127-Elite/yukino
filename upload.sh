#!/bin/bash

# ================= Configuration =================
# Telegram credentials
BOT_TOKEN="8786141502:AAE_Zpl9G_V2bMC7wXhhwfGFcAW0nM4mVRM"
CHAT_ID="6155015997"

# Build Details: Pulls from env vars exported by your main CI script
BUILD_ROM_NAME="${BUILD_ROM:-ROM}"
USER_NAME="${BUILD_USER:-$(whoami)}"
START_TIME="${BUILD_START_TIME:-Unknown}"
FINAL_DURATION="${BUILD_DURATION:-Unknown}"
STATS="${BUILD_STATS:-Unknown}"
VARIANT="${BUILD_VARIANT:-Unknown}"
BTYPE="${BUILD_TYPE:-Unknown}"
RELEASE="${BUILD_RELEASE:-Unknown}"

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

# Generates vertical buttons with Link Emoji and truncates long ROM names
generate_buttons() {
    local buttons=""
    
    local short_zip="${ZIP_NAME}"
    if [[ ${#short_zip} -gt 18 ]]; then
        short_zip="${short_zip:0:18}..."
    fi
    
    if [[ "$BOOT_LINK" != "N/A" ]]; then
        buttons+="[{\"text\": \"🔗 $(escape_html "boot.img ($BOOT_SIZE)")\", \"url\": \"$BOOT_LINK\"}],"
    fi
    if [[ "$VENDOR_BOOT_LINK" != "N/A" ]]; then
        buttons+="[{\"text\": \"🔗 $(escape_html "vendor_boot.img ($VENDOR_BOOT_SIZE)")\", \"url\": \"$VENDOR_BOOT_LINK\"}],"
    fi
    if [[ "$VBMETA_LINK" != "N/A" ]]; then
        buttons+="[{\"text\": \"🔗 $(escape_html "vbmeta.img ($VBMETA_SIZE)")\", \"url\": \"$VBMETA_LINK\"}],"
    fi
    if [[ "$SUPER_EMPTY_LINK" != "N/A" ]]; then
        buttons+="[{\"text\": \"🔗 $(escape_html "super_empty.img ($SUPER_EMPTY_SIZE)")\", \"url\": \"$SUPER_EMPTY_LINK\"}],"
    fi
    if [[ "$DTBO_LINK" != "N/A" ]]; then
        buttons+="[{\"text\": \"🔗 $(escape_html "dtbo.img ($DTBO_SIZE)")\", \"url\": \"$DTBO_LINK\"}],"
    fi
    if [[ "$ROM_LINK" != "N/A" ]]; then
        buttons+="[{\"text\": \"🔗 $(escape_html "${short_zip} ($ROM_SIZE)")\", \"url\": \"$ROM_LINK\"}],"
    fi
    
    buttons="${buttons%,}"
    echo "{\"inline_keyboard\": [$buttons]}"
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
    exit 1
fi

log "Device: $DEVICE"

ROM_ZIP=$(find "$PRODUCT_DIR" -type f -name "*${DEVICE}*.zip" \
    | grep -Ev "ota|symbol|target_files" \
    | sort -r \
    | head -n 1)

if [[ ! -f "$ROM_ZIP" ]]; then
    log "ERROR: ROM ZIP not found"
    exit 1
fi

ZIP_NAME=$(basename "$ROM_ZIP")

# ================= Image Detection =================
BOOT_IMG="$PRODUCT_DIR/boot.img"
VENDOR_BOOT_IMG="$PRODUCT_DIR/vendor_boot.img"
VBMETA_IMG="$PRODUCT_DIR/vbmeta.img"
SUPER_EMPTY_IMG="$PRODUCT_DIR/super_empty.img"
DTBO_IMG="$PRODUCT_DIR/dtbo.img"

[[ ! -f "$BOOT_IMG" ]] && BOOT_IMG="N/A"
[[ ! -f "$VENDOR_BOOT_IMG" ]] && VENDOR_BOOT_IMG="N/A"
[[ ! -f "$VBMETA_IMG" ]] && VBMETA_IMG="N/A"
[[ ! -f "$SUPER_EMPTY_IMG" ]] && SUPER_EMPTY_IMG="N/A"
[[ ! -f "$DTBO_IMG" ]] && DTBO_IMG="N/A"

# ================= File Info Calculation =================
log "Calculating hashes and exact UI sizes..."

fmt_size() {
    local file="$1"
    if [[ "$file" == "N/A" || ! -f "$file" ]]; then
        echo "N/A"
        return
    fi
    
    local bytes=$(stat -c%s "$file")
    awk -v b="$bytes" '
    BEGIN {
        if (b >= 1073741824) { val = b/1073741824; unit = "GiB" }
        else if (b >= 1048576) { val = b/1048576; unit = "MiB" }
        else if (b >= 1024) { val = b/1024; unit = "KiB" }
        else { val = b; unit = "B" }
        
        if (val == int(val)) {
            printf "%d %s", val, unit
        } else {
            printf "%.2f %s", val, unit
        }
    }'
}

get_sha256() {
    if [[ "$1" == "N/A" || ! -f "$1" ]]; then
        echo "N/A"
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}

ROM_SIZE=$(fmt_size "$ROM_ZIP")
BOOT_SIZE=$(fmt_size "$BOOT_IMG")
VENDOR_BOOT_SIZE=$(fmt_size "$VENDOR_BOOT_IMG")
VBMETA_SIZE=$(fmt_size "$VBMETA_IMG")
SUPER_EMPTY_SIZE=$(fmt_size "$SUPER_EMPTY_IMG")
DTBO_SIZE=$(fmt_size "$DTBO_IMG")

ROM_SHA256=$(get_sha256 "$ROM_ZIP")
BOOT_SHA256=$(get_sha256 "$BOOT_IMG")
VENDOR_BOOT_SHA256=$(get_sha256 "$VENDOR_BOOT_IMG")
VBMETA_SHA256=$(get_sha256 "$VBMETA_IMG")
SUPER_EMPTY_SHA256=$(get_sha256 "$SUPER_EMPTY_IMG")
DTBO_SHA256=$(get_sha256 "$DTBO_IMG")

# ================= GoFile Upload Logic =================
log "--------------------------------------------------"
log "Uploading artifacts to GoFile (parallel)..."

upload() {
    [[ "$1" == "N/A" || ! -f "$1" ]] && { echo "N/A"; return; }
    SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name')
    curl -s -F "file=@$1" "https://${SERVER}.gofile.io/uploadFile" \
        | jq -r '.data.downloadPage' 2>/dev/null
}

upload "$ROM_ZIP" > "$TMP_DIR/rom" &
upload "$BOOT_IMG" > "$TMP_DIR/boot" &
upload "$VENDOR_BOOT_IMG" > "$TMP_DIR/vendor_boot" &
upload "$VBMETA_IMG" > "$TMP_DIR/vbmeta" &
upload "$SUPER_EMPTY_IMG" > "$TMP_DIR/super_empty" &
upload "$DTBO_IMG" > "$TMP_DIR/dtbo" &

wait

ROM_LINK=$(cat "$TMP_DIR/rom")
BOOT_LINK=$(cat "$TMP_DIR/boot")
VENDOR_BOOT_LINK=$(cat "$TMP_DIR/vendor_boot")
VBMETA_LINK=$(cat "$TMP_DIR/vbmeta")
SUPER_EMPTY_LINK=$(cat "$TMP_DIR/super_empty")
DTBO_LINK=$(cat "$TMP_DIR/dtbo")

rm -rf "$TMP_DIR"

# ================= Telegram UI Construction =================
log "--------------------------------------------------"
log "Sending UI notification..."

ARTIFACTS_TEXT=""
COUNTER=1

# Formatted with strict 3-space indentation to match video
add_artifact() {
    local name="$1"
    local size="$2"
    local sha="$3"
    local type="IMG"
    [[ "$name" == *.zip ]] && type="ZIP"
    
    ARTIFACTS_TEXT+="${COUNTER}. File: ${name}
   Type: ${type} | Size: ${size}
   SHA256: ${sha}
"
    ((COUNTER++))
}

# Ordered roughly as they appear in standard AOSP outputs/video
add_artifact "$ZIP_NAME" "$ROM_SIZE" "$ROM_SHA256"
[[ "$VENDOR_BOOT_IMG" != "N/A" ]] && add_artifact "vendor_boot.img" "$VENDOR_BOOT_SIZE" "$VENDOR_BOOT_SHA256"
[[ "$VBMETA_IMG" != "N/A" ]] && add_artifact "vbmeta.img" "$VBMETA_SIZE" "$VBMETA_SHA256"
[[ "$SUPER_EMPTY_IMG" != "N/A" ]] && add_artifact "super_empty.img" "$SUPER_EMPTY_SIZE" "$SUPER_EMPTY_SHA256"
[[ "$BOOT_IMG" != "N/A" ]] && add_artifact "boot.img" "$BOOT_SIZE" "$BOOT_SHA256"
[[ "$DTBO_IMG" != "N/A" ]] && add_artifact "dtbo.img" "$DTBO_SIZE" "$DTBO_SHA256"

# Removes trailing newline from blockquote
ARTIFACTS_TEXT=$(echo -n "$ARTIFACTS_TEXT" | sed '$d')

MESSAGE_TEXT=$(cat <<EOF
✅ Build Completed for ${BUILD_ROM_NAME} on ${DEVICE}
User: ${USER_NAME}
Started: ${START_TIME}
Duration: ${FINAL_DURATION}
📊 Build Stats: ${STATS} actions
⚙️ Configuration:
• Variant: ${VARIANT}
• Type: ${BTYPE}
• Release: ${RELEASE}

🎉 Build Artifact(s) Uploaded:
<blockquote><code>${ARTIFACTS_TEXT}</code></blockquote>
EOF
)

REPLY_MARKUP_JSON=$(generate_buttons)

send_telegram_text "$MESSAGE_TEXT" "$REPLY_MARKUP_JSON"

log "UI notification sent."
log "--------------------------------------------------"
log "Script finished."
