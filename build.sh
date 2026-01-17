#!/bin/bash
# [2026-01-17] KubeCuro Production Build System
# Version: 3.0 (Static-Hardened, Auto-Purge, PEP 668 Compliant)
# Properly commented throughout for maintainability.

# --- OS DETECTION ---
# Identify the binary directory inside the virtual environment for cross-platform safety.
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    PYINSTALLER_SEPARATOR=";"
    PYTHON_EXE="python"
    VENV_BIN="Scripts"
else
    PYINSTALLER_SEPARATOR=":"
    PYTHON_EXE="python3"
    VENV_BIN="bin"
fi

# --- ANCHOR THE DIRECTORY ---
# Ensure the script runs relative to its own folder.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- CLEANUP TRAP ---
# Handle script exits, restore cursor visibility, and report failures.
LOG_FILE=$(mktemp)
cleanup() {
    local exit_code=$?
    tput cnorm 
    if [ "$exit_code" -ne 0 ] && [ "$exit_code" -ne 130 ]; then
        echo -e "\n\033[31m💥 Build interrupted or failed. See logs at: $LOG_FILE\033[0m"
    fi
    rm -f "$LOG_FILE"
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

# --- SPINNER FUNCTION ---
# Provides visual feedback for backgrounded tasks.
spinner() {
    local pid="$1"
    local delay=0.1
    local spinstr='|/-\\'
    tput civis 
    while ps -p "$pid" > /dev/null 2>&1; do
        local temp="${spinstr#?}"
        printf " [%c] " "$spinstr"
        spinstr="$temp${spinstr%"$temp"}"
        sleep "$delay"
        printf "\b\b\b\b\b"
    done
    wait "$pid"
    local res=$?
    printf "     \b\b\b\b\b"
    tput cnorm 
    return "$res"
}

# --- PRE-FLIGHT ---
echo -e "\033[1;35m🧬 KubeCuro Build System\033[0m"
echo "--------------------------------------"

# 1. System Dependencies
# Ensures patchelf and python-dev are present to allow StaticX to compile.
echo -n "🔍 Verifying System Dependencies..."
MISSING_TOOLS=()
! command -v $PYTHON_EXE &> /dev/null && MISSING_TOOLS+=("python3")
! command -v patchelf &> /dev/null && MISSING_TOOLS+=("patchelf")
! command -v strip &> /dev/null && MISSING_TOOLS+=("binutils")

# Check for Ubuntu dev headers specifically
if ! dpkg -s python3-dev >/dev/null 2>&1; then
    MISSING_TOOLS+=("python3-dev")
fi

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo -e "[\033[33m${MISSING_TOOLS[*]} MISSING\033[0m]"
    sudo -v
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip python3-dev patchelf binutils musl-tools
    fi
else
    echo -e "[DONE]"
    sudo -v &>/dev/null
fi

# 2. Virtual Environment Setup & StaticX Installation
VENV_DIR="$SCRIPT_DIR/.venv_build"
VP_PIP="$VENV_DIR/$VENV_BIN/pip"
VP_PYINSTALLER="$VENV_DIR/$VENV_BIN/pyinstaller"
VP_STATICX="$VENV_DIR/$VENV_BIN/staticx"

echo -n "🌐 Initializing Isolated Build Environment..."
{
    [ ! -d "$VENV_DIR" ] && $PYTHON_EXE -m venv "$VENV_DIR"
    "$VP_PIP" install --upgrade pip setuptools wheel
    # Install staticx inside the venv so it is available for hardening.
    "$VP_PIP" install staticx
} > "$LOG_FILE" 2>&1 &
spinner "$!" || { echo -e "[\033[31mFAIL\033[0m]"; echo -e "\033[31mError during Initializing VENV. \033[0m"; cat "$LOG_FILE"; exit 1; }
echo -e "[DONE]"

# 3. Dependency Sync
echo -n "📦 Synchronizing requirements.txt..."
{
    "$VP_PIP" install -r "$SCRIPT_DIR/requirements.txt"
} > "$LOG_FILE" 2>&1 &
spinner "$!" || { echo -e "[\033[31mFAIL\033[0m]"; echo -e "\033[31mError during Synchronizing requirements. \033[0m"; cat "$LOG_FILE"; exit 1; }
echo -e "[DONE]"

# 4. Cleaning
echo -n "🧹 Purging old build artifacts..."
rm -rf build/ dist/ *.spec src/*.egg-info &
spinner "$!" || { echo -e "[\033[31mFAIL\033[0m]"; echo -e "\033[31mError during Purging old build artifacts. \033[0m"; exit 1; }
echo -e "[DONE]"

# 5. Building Dynamic Binary
echo -n "🐍 Compiling Dynamic Binary (Stripped)..."
ASSETS_DIR="$SCRIPT_DIR/catalog"
{
    "$VP_PYINSTALLER" --onefile --clean --name kubecuro_dynamic \
                --paths "$SCRIPT_DIR/src" \
                --add-data "${ASSETS_DIR}${PYINSTALLER_SEPARATOR}catalog" \
                --collect-all rich \
                --collect-all rich_click \
                --collect-all ruamel.yaml \
                --hidden-import argcomplete \
                --hidden-import ruamel.yaml \
                --exclude-module _ruamel_yaml_clib \
                --exclude-module ruamel.yaml.clib \
                --strip \
                "$SCRIPT_DIR/src/kubecuro/cli/main.py"
} > "$LOG_FILE" 2>&1 &
spinner "$!" || { echo -e "[\033[31mFAIL\033[0m]"; echo -e "\033[31mError during compilation. Build Log:\033[0m"; cat "$LOG_FILE"; exit 1; }
echo -e "[DONE]"

# 6. StaticX Hardening
# Store the size of the dynamic binary for analytics before processing.
RAW_SIZE_BYTES=$(stat -c%s "dist/kubecuro_dynamic" 2>/dev/null || stat -f%z "dist/kubecuro_dynamic" || echo 0)

if [ -f "$VP_STATICX" ]; then
    echo -n "🛡️  Hardening to Static (Portable) Binary..."
    ( "$VP_STATICX" --strip dist/kubecuro_dynamic dist/kubecuro > "$LOG_FILE" 2>&1 ) &
    if spinner "$!" && [ -f "dist/kubecuro" ]; then
        echo -e "[DONE]"
        BUILD_TYPE="Static (Portable)"
    else
        echo -e "[\033[31mFAIL\033[0m]"
        echo -e "\033[33m⚠️  StaticX failed. Falling back to dynamic.\033[0m"
        cp "dist/kubecuro_dynamic" "dist/kubecuro"
        BUILD_TYPE="Dynamic (StaticX Error)"
    fi
else
    cp "dist/kubecuro_dynamic" "dist/kubecuro"
    BUILD_TYPE="Dynamic (No StaticX)"
fi

# 7. Integrity Check
echo -n "🧪 Running Binary Integrity Check..."
if ./dist/kubecuro --version > /dev/null 2>&1; then
    echo -e "[\033[32mPASSED\033[0m]"
else
    echo -e "[\033[31mFAILED\033[0m]"
    echo -e "❌ \033[31mBinary execution test failed. Check dependencies.\033[0m"
    exit 1
fi

# 8. Global Installation
echo -n "🚚 Installing to /usr/local/bin..."
if sudo cp ./dist/kubecuro /usr/local/bin/kubecuro && sudo chmod +x /usr/local/bin/kubecuro; then
    echo -e "[\033[32mDONE\033[0m]"
    INSTALLED=true
else
    echo -e "[\033[33mSKIPPED\033[0m]"
    INSTALLED=false
fi

# 9. Automatic Venv Purge
if [ -d "$VENV_DIR" ]; then
    echo -n "🗑️  Auto-purging build environment..."
    rm -rf "$VENV_DIR"
    echo -e "[DONE]"
fi

# --- SUMMARY & ANALYTICS ---
FINAL_SIZE_BYTES=$(stat -c%s "dist/kubecuro" 2>/dev/null || stat -f%z "dist/kubecuro" || echo 0)
FINAL_SIZE_HUMAN=$(du -h "dist/kubecuro" | cut -f1)

# Logic to only show reduction if the size actually decreased.
if [ "$RAW_SIZE_BYTES" -gt "$FINAL_SIZE_BYTES" ] && [ "$RAW_SIZE_BYTES" -gt 0 ]; then
    SAVED_PERCENT=$(( 100 * (RAW_SIZE_BYTES - FINAL_SIZE_BYTES) / RAW_SIZE_BYTES ))
    SIZE_OUTPUT="\033[1;33m$FINAL_SIZE_HUMAN\033[0m (Reduced $SAVED_PERCENT%)"
else
    SIZE_OUTPUT="\033[1;33m$FINAL_SIZE_HUMAN\033[0m"
fi

echo "--------------------------------------"
echo -e "✅ \033[1;32mBuild & Deployment Complete!\033[0m"
echo -e "💎 Type:      \033[1;34m$BUILD_TYPE\033[0m"
echo -e "📦 Size:      $SIZE_OUTPUT"
if [ "$INSTALLED" = true ]; then
    echo -e "🚀 Global:    \033[1;32m'kubecuro' is available globally.\033[0m"
fi
echo "--------------------------------------"
