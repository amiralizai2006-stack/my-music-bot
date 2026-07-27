#!/bin/bash
# Telegram Music Bot - Startup Script with Termux/Android support

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo "🎵 Telegram Music Bot - Starting up..."

# Check if we're in the right directory
cd "$PROJECT_DIR"

# Detect platform
IS_TERMUX=false
IS_ANDROID=false
if [[ "$PREFIX" == *"com.termux"* ]] || [[ -n "$TERMUX_VERSION" ]] || [[ "$(uname -o 2>/dev/null)" == "Android" ]]; then
    IS_TERMUX=true
    IS_ANDROID=true
fi

# Check for config
if [ ! -f "config.py" ]; then
    echo "⚠️  config.py not found!"
    echo "   Copy config.example.py to config.py and fill in your credentials:"
    echo "   cp config.example.py config.py"
    echo "   # Then edit config.py with your API_ID, API_HASH, BOT_TOKEN"
    echo ""
    echo "   Or set environment variables:"
    echo "   export API_ID=1234567"
    echo "   export API_HASH=your_api_hash"
    echo "   export BOT_TOKEN=your_bot_token"
    echo "   export ADMIN_IDS=123456789,987654321"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip > /dev/null

# Install requirements based on platform
echo "📦 Installing dependencies..."

# Always install base requirements
pip install -r requirements-base.txt > /dev/null

# Install Linux-specific requirements (voice chat) if not on Android
if [ "$IS_ANDROID" = false ]; then
    echo "   Installing voice chat dependencies (Linux)..."
    pip install -r requirements-linux.txt > /dev/null 2>&1 || {
        echo "⚠️  Warning: Could not install voice chat dependencies."
        echo "   Voice chat may not work. You can try manually:"
        echo "   pip install pytgcalls"
    }
else
    echo "   Android/Termux detected - skipping voice chat dependencies (not supported)"
    echo "   Only music download features will work."
fi

# Check for ffmpeg (required for audio conversion)
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  ffmpeg not found! Audio conversion may fail."
    if [ "$IS_TERMUX" = true ]; then
        echo "   Install with: pkg install ffmpeg"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "   Install with: sudo apt install ffmpeg  (Ubuntu/Debian)"
        echo "   Or: sudo dnf install ffmpeg  (Fedora)"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "   Install with: brew install ffmpeg"
    fi
fi

# Create necessary directories
mkdir -p downloads data logs

# Start the bot
echo "🚀 Starting bot..."
echo "   Press Ctrl+C to stop"
echo ""

# Run the bot
if [ "$IS_ANDROID" = true ]; then
    echo "ℹ️  Running in LIMITED MODE (Termux/Android)"
    echo "   Voice chat features are NOT available on this platform."
    echo "   Only music download (/play) will work."
    echo ""
fi

python main.py