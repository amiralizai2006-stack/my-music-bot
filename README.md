# 🎵 Telegram Music Bot

A self-hosted Telegram bot for playing music in group voice calls using **Pyrogram** + **PyTgCalls**.

Supports YouTube, SoundCloud, and direct links. Features queue management, volume control, repeat modes, and admin controls.

> **📱 Termux/Android Support:** The bot now works on Termux! Voice chat is not available on Android (due to missing `tgcalls` native library), but music search & download works perfectly.

---

## ✨ Features

| Feature | Linux/Windows/macOS | Android/Termux |
|---------|---------------------|----------------|
| 🎶 Music search & download | ✅ | ✅ |
| 🎤 Voice chat playback | ✅ | ❌ (not supported) |
| 📋 Queue management | ✅ | ✅ |
| 🔊 Volume control | ✅ | N/A |
| 🔁 Repeat modes | ✅ | N/A |
| 👑 Admin controls | ✅ | ✅ |

---

## 🚀 Quick Start

### 1. Get Credentials

| Credential | Source |
|------------|--------|
| `API_ID`, `API_HASH` | https://my.telegram.org/apps |
| `BOT_TOKEN` | @BotFather |

### 2. Install & Run

#### Linux / macOS / Windows (Full Features)

```bash
# Clone the repo
git clone https://github.com/mehrshadharry/tg-music-bot.git
cd tg-music-bot

# Configure
cp config.example.py config.py
# Edit config.py with your credentials
# OR set environment variables (see below)

# Run
chmod +x run.sh
./run.sh
```

#### Termux / Android (Limited - Download Only)

```bash
# In Termux
pkg install python ffmpeg git
git clone https://github.com/mehrshadharry/tg-music-bot.git
cd tg-music-bot

# Configure
cp config.example.py config.py
# Edit config.py

# Run (voice chat will be disabled automatically)
chmod +x run.sh
./run.sh
```

---

## ⚙️ Configuration

### Option A: Environment Variables (Recommended)

```bash
export API_ID=1234567
export API_HASH=abcdef1234567890abcdef1234567890
export BOT_TOKEN=123456789:ABC-DEFghIJKlmNoPQRsTUVwxyZ
export ADMIN_IDS=123456789,987654321  # Optional

./run.sh
```

### Option B: config.py File

```bash
cp config.example.py config.py
nano config.py  # Fill in your values
```

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `API_ID`, `API_HASH`, `BOT_TOKEN` | **Required** Telegram credentials | — |
| `ADMIN_IDS` | Comma-separated user IDs for admin commands | (empty = all users) |
| `DEFAULT_VOLUME` | Default volume (0-200) | `100` |
| `AUTO_LEAVE_TIMEOUT` | Auto-leave after inactivity (seconds, 0=disabled) | `300` |
| `ENABLE_VOICE_CHAT` | Enable voice chat (auto-disabled on Android) | `true`/`false` |
| `YTDL_FORMAT` | yt-dlp format selector | `bestaudio/best` |

---

## 🐳 Systemd Service (Production Linux)

```bash
# Copy service file
sudo cp tg-music-bot.service /etc/systemd/system/

# Edit with your credentials
sudo nano /etc/systemd/system/tg-music-bot.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now tg-music-bot

# View logs
sudo journalctl -u tg-music-bot -f
```

**Service file** uses environment variables - edit the `Environment=` lines.

---

## 🎮 Commands

### All Platforms

| Command | Description |
|---------|-------------|
| `/play <song name or URL>` | Search/download & add to queue |
| `/queue` | Show current queue |
| `/clear` | Clear queue (admin only) |
| `/help` | Show help |

### Voice Chat Only (Linux/Windows/macOS)

| Command | Description | Admin? |
|---------|-------------|--------|
| `/skip` | Skip current track | ❌ |
| `/pause` | Pause playback | ❌ |
| `/resume` | Resume playback | ❌ |
| `/stop` | Stop & leave call | ❌ |
| `/now` | Show now playing | ❌ |
| `/volume <0-200>` | Set volume | ❌ |
| `/repeat <off\|one\|all>` | Set repeat mode | ✅ |
| `/leave` | Force leave call | ✅ |

### Inline Buttons

The `/queue` and `/now` commands show interactive buttons for:
- ⏭ Skip / ⏸ Pause / ▶️ Resume
- 🔊 Volume + / 🔉 Volume -
- 🗑 Clear queue (admin)

---

## 📁 Project Structure

```
tg-music-bot/
├── main.py                 # Entry point
├── config.py               # Configuration (from config.example.py)
├── config.example.py       # Template config
├── requirements.txt        # Base requirements (all platforms)
├── requirements-base.txt   # Core deps (pyrogram, yt-dlp, etc.)
├── requirements-linux.txt  # Voice chat deps (pytgcalls, psutil)
├── run.sh                  # Smart startup script
├── tg-music-bot.service    # Systemd service
├── optional_deps.py        # Platform detection & optional imports
├── database.py             # SQLite queue & settings
├── player.py               # Downloader & PyTgCalls wrapper
├── handlers.py             # Command handlers
├── downloads/              # Downloaded audio files
├── data/                   # SQLite database
└── logs/                   # Log files
```

---

## 🔧 Troubleshooting

### Termux / Android Issues

| Problem | Solution |
|---------|----------|
| `No matching distribution for tgcalls` | **Expected** - voice chat not supported on Android. Use Linux for voice chat. |
| `psutil: platform android not supported` | **Fixed** - psutil is now optional, bot works without it. |
| `ffmpeg not found` | Run `pkg install ffmpeg` in Termux |
| `ModuleNotFoundError: pyrogram` | Run `pip install -r requirements-base.txt` |

### Linux Issues

| Problem | Solution |
|---------|----------|
| Bot doesn't join voice chat | Make bot **admin** with "Manage Voice Chats" permission |
| "No active group call" | Start a voice chat in the group first |
| Audio distorted/quiet | Check `DEFAULT_VOLUME` (0-200), install `ffmpeg` |
| `pytgcalls` import error | `pip install -r requirements-linux.txt` |
| FloodWait errors | Wait - bot auto-retries |

### General

| Problem | Solution |
|---------|----------|
| Config errors on startup | Check `API_ID`, `API_HASH`, `BOT_TOKEN` are set correctly |
| Database locked | Delete `data/music_bot.db` and restart |
| yt-dlp fails on some videos | Update: `pip install --upgrade yt-dlp` |

---

## 📦 Requirements Breakdown

### requirements-base.txt (All Platforms)
```
pyrogram>=2.0
yt-dlp>=2024.1.1
python-dotenv>=1.0
pydantic>=2.0
aiohttp>=3.9
aiosqlite>=0.19
```

### requirements-linux.txt (Voice Chat - Linux Only)
```
pytgcalls>=4.0
psutil>=5.9
```

> **Note:** `tgcalls` (the native library) is installed automatically with `pytgcalls` on Linux. No manual compilation needed.

---

## 🛠 Development

### Run in Development Mode

```bash
# With auto-reload (install watchdog first)
pip install watchdog
python main.py
```

### Code Style

```bash
# Format
pip install black isort
black .
isort .
```

### Testing

```bash
# Test imports
python -c "import config, database, player, handlers, optional_deps; print('OK')"
```

---

## 📄 License

MIT License - Feel free to use, modify, and distribute.

---

## 🙏 Credits

- [Pyrogram](https://github.com/pyrogram/pyrogram) - Telegram MTProto API
- [PyTgCalls](https://github.com/pytgcalls/pytgcalls) - Telegram Voice Calls
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video/Audio downloader

---

## 💬 Support

- **Issues:** [GitHub Issues](https://github.com/mehrshadharry/tg-music-bot/issues)
- **Telegram:** [Mehrshad](https://t.me/mehrshadharry)

---

**Made with ❤️ for the Telegram community**