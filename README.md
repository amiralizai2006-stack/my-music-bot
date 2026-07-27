# 🎵 Telegram Music Bot

A self-hosted Telegram bot for playing music in group voice calls using **Pyrogram** + **PyTgCalls**.

## ✨ Features

- 🎶 Play music from YouTube, SoundCloud, and direct links
- 🔍 Search by song name (no link needed)
- 📋 Queue management with inline buttons
- ⏯ Play/Pause/Skip/Stop controls
- 🔊 Volume control (0-200%)
- 🔁 Repeat modes (off / one / all)
- 👥 Admin-only commands
- 💾 Persistent queue (SQLite)
- 📦 Auto-download & convert to MP3 (yt-dlp + ffmpeg)
- 🚀 Auto-leave after inactivity
- 🐳 Systemd service support

## 📋 Requirements

- Python 3.10+
- ffmpeg (for audio conversion)
- Telegram API credentials (API_ID, API_HASH)
- Bot token from @BotFather

## 🚀 Quick Start

### 1. Clone & Setup

```bash
cd /data/workspace/tg-music-bot
cp config.example.py config.py
# Edit config.py with your credentials
```

### 2. Get Credentials

| Credential | Source |
|------------|--------|
| `API_ID`, `API_HASH` | https://my.telegram.org/apps |
| `BOT_TOKEN` | @BotFather |
| `ADMIN_IDS` | Your user ID (get from @userinfobot) |

### 3. Install & Run

```bash
# Make script executable (once)
chmod +x run.sh

# Run the bot
./run.sh
```

Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 🐳 Systemd Service (Production)

```bash
# Copy service file
sudo cp tg-music-bot.service /etc/systemd/system/

# Edit with your credentials
sudo nano /etc/systemd/system/tg-music-bot.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now tg-music-bot

# Check status
sudo systemctl status tg-music-bot
sudo journalctl -u tg-music-bot -f
```

## 🎮 Commands

| Command | Description | Admin Only |
|---------|-------------|------------|
| `/play <song/link>` | Add to queue & play | ❌ |
| `/queue` | Show queue with controls | ❌ |
| `/skip` | Skip current track | ❌ |
| `/pause` | Pause playback | ❌ |
| `/resume` | Resume playback | ❌ |
| `/stop` | Stop & leave call | ❌ |
| `/now` | Show current track | ❌ |
| `/volume <0-200>` | Set volume | ❌ |
| `/repeat <off/one/all>` | Set repeat mode | ✅ |
| `/clear` | Clear queue | ✅ |
| `/leave` | Force leave call | ✅ |

## 🎯 Usage Flow

1. **Add bot to group** and make it **admin** (with "Manage Voice Chats" permission)
2. **Join a group voice call** yourself
3. **Send `/play <song name or YouTube link>`** in the group
4. Bot joins the call and starts playing!

## 📁 Project Structure

```
tg-music-bot/
├── main.py              # Entry point
├── config.py            # Configuration (create from config.example.py)
├── config.example.py    # Template config
├── requirements.txt     # Python dependencies
├── run.sh              # Startup script
├── tg-music-bot.service # Systemd service
├── database.py         # SQLite queue & settings
├── player.py           # Downloader & PyTgCalls wrapper
├── handlers.py         # Command handlers
├── downloads/          # Downloaded audio files
├── data/               # SQLite database
└── logs/               # Log files
```

## ⚙️ Configuration

All settings in `config.py` or via environment variables:

```python
# Required
api_id = 1234567
api_hash = "your_api_hash"
bot_token = "123456:ABC-DEF..."

# Optional
admin_ids = [123456789, 987654321]  # Admin-only commands
command_prefix = "/"                  # Command prefix
default_volume = 100                  # 0-200
auto_leave_timeout = 300              # Seconds (0 = disabled)
max_queue_size = 50
ytdl_format = "bestaudio/best"
```

## 🔧 Troubleshooting

### Bot doesn't join voice chat
- Ensure bot is **admin** with "Manage Voice Chats" permission
- You must be **in the voice chat** when sending `/play`

### Audio not playing / distorted
- Install ffmpeg: `sudo apt install ffmpeg`
- Check logs: `journalctl -u tg-music-bot -f`

### "No active group call" error
- Start a voice chat in the group first
- Then send `/play`

### yt-dlp errors
- Update yt-dlp: `pip install --upgrade yt-dlp`
- Some videos may be geo-blocked or age-restricted

## 📝 License

MIT License - Feel free to use and modify.

## 🙏 Credits

- [Pyrogram](https://github.com/pyrogram/pyrogram) - Telegram MTProto API
- [PyTgCalls](https://github.com/pytgcalls/pytgcalls) - Telegram Voice Calls
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video/audio downloader