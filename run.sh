#!/bin/bash
# Telegram Music Bot - Startup Script

set -e

PROJECT_DIR="/data/workspace/tg-music-bot"
VENV_DIR="$PROJECT_DIR/venv"

echo "🎵 Telegram Music Bot - Starting up..."

# Check if we're in the right directory
cd "$PROJECT_DIR"

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

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt > /dev/null

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  ffmpeg not found! Audio conversion may fail."
    echo "   Install with: sudo apt install ffmpeg (Ubuntu/Debian)"
    echo "   Or: brew install ffmpeg (macOS)"
fi

# Create necessary directories
mkdir -p downloads data logs

# Start the bot
echo "🚀 Starting bot..."
echo "   Press Ctrl+C to stop"
echo ""

python main.py