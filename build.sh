#!/bin/bash
"""
KUBECURO BUILD SYSTEM
---------------------
Handles system dependencies, virtual environment isolation, 
compilation, and static hardening.

Requirements: python3, pip, binutils, patchelf (Linux)
"""

# --- OS DETECTION ---
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    PYINSTALLER_SEPARATOR=";"
    PYTHON_EXE="python"
else
    PYINSTALLER_SEPARATOR=":"
    PYTHON_EXE="python3"
fi

# --- ANCHOR THE DIRECTORY ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- CLEANUP TRAP ---
LOG_FILE=$(mktemp)
cleanup() {
    local exit_code=$?
    tput cnorm 
    if [ -n "$VIRTUAL_ENV" ]; then deactivate 2>/dev/null; fi
    
    # Restored failure message
    if [ "$exit_code" -ne 0 ] && [ "$exit_code" -ne 130 ]; then
        echo -e "\n\033[31m💥 Build interrupted or failed. See logs above.\033[0m"
    fi
    
    rm -f "$LOG_FILE"
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

# --- SPINNER FUNCTION ---
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

# 1. Python & System Tooling (patchelf, binutils)
echo -n "🔍 Verifying System Dependencies..."
MISSING_TOOLS=()
! command -v $PYTHON_EXE &> /dev/null && MISSING_TOOLS+=("python3")
! command -v patchelf &> /dev/null && [[ "$OSTYPE" == "linux-gnu"* ]] && MISSING_TOOLS+=("patchelf")
! command -v strip &> /dev/null && MISSING_TOOLS+=("binutils")

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo -e "[\033[33m${MISSING_TOOLS[*]} MISSING\033[0m]"
    echo -e "🔐 \033[1mAdmin privileges required for system tools...\033[0m"
    sudo -v # Prime sudo session early
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip patchelf binutils
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y python3 patchelf binutils
        else
            echo -e "❌ \033[31mManual install required for: ${MISSING_TOOLS[*]}\033[0m"
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install python binutils
        fi
    fi
else
    echo -e "[DONE]"
	sudo -v &>/dev/null
fi

# 2. Virtual Environment Setup
VENV_DIR="$SCRIPT_DIR/.venv_build"
echo -n "🌐 Initializing Isolated Build Environment..."
{
    if [ ! -d "$VENV_DIR" ]; then
        $PYTHON_EXE -m venv "$VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate" || source "$VENV_DIR/Scripts/activate"
    pip install --upgrade pip setuptools wheel
} > "$LOG_FILE" 2>&1 &
if spinner "$!"; then
    echo -e "[DONE]"
else
    echo -e "[\033[31mFAIL\033[0m]"
    cat "$LOG_FILE"
    exit 1
fi

# 3. Dependency Sync
echo -n "📦 Synchronizing requirements.txt..."
{
    pip install -r "$SCRIPT_DIR/requirements.txt"
} > "$LOG_FILE" 2>&1 &
if spinner "$!"; then
    echo -e "[DONE]"
else
    echo -e "[\033[31mFAIL\033[0m]"
    cat "$LOG_FILE"
    exit 1
fi

# 4. Cleaning
echo -n "🧹 Purging old build artifacts..."
{
	rm -rf build/ dist/ *.spec src/*.egg-info
} &
spinner "$!"
echo -e "[DONE]"

# 5. Building
echo -n "🐍 Compiling Dynamic Binary (Stripped)..."
ASSETS_DIR="$SCRIPT_DIR/catalog"
{
    # --strip uses binutils to remove debug symbols
    pyinstaller --onefile --clean --name kubecuro_dynamic \
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

if spinner "$!"; then
    echo -e "[DONE]"
else
    echo -e "[\033[31mFAIL\033[0m]"
    echo -e "\033[31mError during compilation. Build Log:\033[0m"
    echo "--------------------------------------"
    cat "$LOG_FILE"
    echo "--------------------------------------"
    exit 1
fi

# 6. StaticX Hardening
RAW_SIZE_BYTES=$(stat -c%s "dist/kubecuro_dynamic" 2>/dev/null || stat -f%z "dist/kubecuro_dynamic")
RAW_SIZE_HUMAN=$(du -h "dist/kubecuro_dynamic" | cut -f1)

if command -v staticx &> /dev/null; then
    echo -n "🛡️  Hardening to Static Binary..."
    (staticx --strip dist/kubecuro_dynamic dist/kubecuro > "$LOG_FILE" 2>&1) &
    if spinner "$!"; then
        echo -e "[DONE]"
        BUILD_TYPE="Static (Portable)"
    else
        echo -e "[\033[31mFAIL\033[0m]"
        echo -e "\033[33mStaticX failed. Falling back to dynamic.\033[0m"
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
# Copy the verified binary to the system path.
echo -n "🚚 Installing to /usr/local/bin..."
if sudo cp ./dist/kubecuro /usr/local/bin/kubecuro && sudo chmod +x /usr/local/bin/kubecuro; then
    echo -e "[\033[32mDONE\033[0m]"
    INSTALLED=true
else
    echo -e "[\033[33mSKIPPED\033[0m]"
    INSTALLED=false
fi

# 9. Venv Purge Logic
# Ask the user if they want to reclaim disk space by removing the venv.
echo "--------------------------------------"
read -p "🗑️  Purge build environment (.venv_build)? [y/N]: " PURGE_VENV
if [[ "$PURGE_VENV" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    VENV_SIZE=$(du -sh "$VENV_DIR" | cut -f1)
    rm -rf "$VENV_DIR"
    echo -e "\033[1;32m✨ Cleaned up $VENV_SIZE of build artifacts.\033[0m"
fi

# --- SUMMARY & ANALYTICS ---
# Final size calculations with Division-by-Zero safety.
FINAL_SIZE_BYTES=$(stat -c%s "dist/kubecuro" 2>/dev/null || stat -f%z "dist/kubecuro" || echo 0)
FINAL_SIZE_HUMAN=$(du -h "dist/kubecuro" | cut -f1)

SAVED_PERCENT=0
if [ "$RAW_SIZE_BYTES" -gt 0 ]; then
    SAVED_PERCENT=$(( 100 * (RAW_SIZE_BYTES - FINAL_SIZE_BYTES) / RAW_SIZE_BYTES ))
fi

echo "--------------------------------------"
echo -e "✅ \033[1;32mBuild & Deployment Complete!\033[0m"
echo -e "💎 Type:      \033[1;34m$BUILD_TYPE\033[0m"
echo -e "📦 Size:      \033[1;33m$FINAL_SIZE_HUMAN\033[0m (Saved $SAVED_PERCENT%)"
if [ "$INSTALLED" = true ]; then
    echo -e "🚀 Global:    \033[1;32m'kubecuro' is now available globally.\033[0m"
else
    echo -e "🚀 Local:     \033[1;36m./dist/kubecuro\033[0m"
fi
echo "--------------------------------------"


