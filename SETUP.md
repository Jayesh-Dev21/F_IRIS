# IRIS Setup Guide

Comprehensive guide to setting up and configuring IRIS Security Agent.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [OpenAI API Setup](#openai-api-setup)
4. [Telegram Bot Setup](#telegram-bot-setup)
5. [Configuration](#configuration)
6. [Testing](#testing)
7. [Running IRIS](#running-iris)
8. [Advanced Configuration](#advanced-configuration)

---

## Prerequisites

### System Requirements

- **Operating System**: Linux, macOS, or Windows
- **Python**: 3.10 or higher
- **Camera**: Webcam or USB camera
- **RAM**: 2GB minimum (4GB recommended)
- **Disk Space**: 500MB + storage for snapshots

### Required Accounts

- **OpenAI Account** with API access (required)
- **Telegram Account** (optional, for alerts)

---

## Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/Aerex0/IRIS
cd IRIS
```

### Step 2: Install uv (if not already installed)

**Linux/macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Step 3: Install Dependencies

```bash
# uv automatically creates a virtual environment and installs everything
uv sync
```

**That's it!** uv handles:
- Creating `.venv/` virtual environment
- Installing all dependencies from `pyproject.toml`
- Resolving and locking dependencies in `uv.lock`

**Troubleshooting:**

If on Raspberry Pi, install system dependencies first:
```bash
sudo apt-get update
sudo apt-get install -y libatlas-base-dev
```

---

## OpenAI API Setup

### Step 1: Get API Key

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to **API Keys** section
4. Click **Create new secret key**
5. Copy the key (starts with `sk-`)

### Step 2: Add Credits

1. Go to **Billing** section
2. Add payment method
3. Purchase credits ($5-10 recommended for testing)

### Step 3: Configure API Key

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=sk-your-actual-api-key-here
```

**Cost Estimates:**
- GPT-4o Vision: ~$0.01 per analysis
- Average: 10-50 events/day = $0.10-0.50/day
- Monthly: ~$3-15 depending on activity

---

## Telegram Bot Setup

### Step 1: Create Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Choose a name: `IRIS Security Bot`
4. Choose username: `your_iris_bot` (must end in 'bot')
5. Copy the **bot token** (looks like `123456:ABC-DEF...`)

### Step 2: Get Chat ID

**Method 1: Use IDBot**
1. Search for **@userinfobot** in Telegram
2. Send `/start`
3. Copy your **chat ID** (numbers only)

**Method 2: Manual**
1. Send a message to your bot
2. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   (Replace `<TOKEN>` with your bot token)
3. Find `"chat":{"id":123456789}` in the response
4. Copy the ID number

### Step 3: Configure Telegram

Add to `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF-your-bot-token
TELEGRAM_CHAT_ID=123456789
```

### Step 4: Test Connection

```bash
uv run src/main.py test-alert
```

You should receive a test message on Telegram!

---

## Configuration

### Basic Configuration

Edit `config/settings.yaml`:

```yaml
camera:
  device_id: 0              # 0 = default webcam, 1 = external
  fps: 30
  resolution: [1280, 720]   # Width x Height

monitoring:
  active: true
  motion_threshold: 25      # 0-100 (lower = more sensitive)
  min_motion_area: 500      # Minimum pixels to trigger
  cooldown_seconds: 5       # Time between analyses

intelligence:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.3          # Lower = more consistent

alerts:
  enabled: true
  telegram:
    enabled: true
    alert_on_threat_level: "medium"  # none, low, medium, high
    include_snapshot: true
```

### Camera Configuration

**Find your camera device:**

```bash
# Test default camera
uv run src/main.py test-camera

# If that fails, try other device IDs in settings.yaml:
camera:
  device_id: 1  # Try 0, 1, 2, etc.
```

**Common device IDs:**
- `0` - Built-in laptop webcam
- `1` - First USB camera
- `2` - Second USB camera

**Adjust resolution** based on your camera:
```yaml
camera:
  resolution: [1920, 1080]  # Full HD
  resolution: [1280, 720]   # HD (recommended)
  resolution: [640, 480]    # SD (lower quality, faster)
```

### Motion Detection Tuning

**Too sensitive** (too many false alerts):
```yaml
monitoring:
  motion_threshold: 35      # Increase
  min_motion_area: 1000     # Increase
```

**Not sensitive enough** (missing events):
```yaml
monitoring:
  motion_threshold: 15      # Decrease
  min_motion_area: 300      # Decrease
```

**Test motion detection:**
```bash
uv run src/main.py start --show-video
```

Green boxes should appear when you move. Adjust until satisfied.

### Alert Configuration

**Alert only on high threats:**
```yaml
alerts:
  telegram:
    alert_on_threat_level: "high"
```

**Disable alerts temporarily:**
```yaml
alerts:
  enabled: false
```

**Disable snapshots in alerts:**
```yaml
alerts:
  telegram:
    include_snapshot: false
```

---

## Testing

### Test 1: Camera

```bash
uv run src/main.py test-camera
```

**Expected:** Video window opens showing camera feed  
**If fails:** Check device_id in config, try different values

### Test 2: Telegram

```bash
uv run src/main.py test-alert
```

**Expected:** Test message appears in Telegram  
**If fails:** Check bot token and chat ID in .env

### Test 3: Motion Detection

```bash
uv run src/main.py start --show-video
```

**Expected:** 
- Video window opens
- Green boxes appear when you move
- Console shows "Motion detected" messages

**If no detection:**
- Lower `motion_threshold` in config
- Ensure good lighting
- Try waving hand in front of camera

### Test 4: Full System

```bash
uv run src/main.py start
```

Move in front of camera and wait 5-10 seconds.

**Expected:**
- Console shows "Motion detected - Analyzing..."
- Analysis result appears
- Telegram alert received (if threat >= medium)
- Event stored in database

**Verify:**
```bash
uv run src/main.py query query --last 1h
```

---

## Advanced Configuration

### Custom Prompts

Edit `config/prompts/security.txt` to customize how IRIS analyzes scenes.

Example - More relaxed assessment:
```
You are IRIS, a friendly security monitoring AI.

Analyze scenes and only report genuine concerns.
Most daily activities should be classified as "normal" with "none" threat.
Only flag truly unusual or suspicious behavior.

...
```

### Multiple Configurations

Create environment-specific configs:

```bash
# config/home.yaml - relaxed for home use
# config/office.yaml - strict for office

# Run with specific config
uv run src/main.py start --config config/office.yaml
```

### Database Management

**View database directly:**
```bash
sqlite3 data/events.db "SELECT * FROM events ORDER BY timestamp DESC LIMIT 10;"
```

**Backup database:**
```bash
cp data/events.db backups/events_$(date +%Y%m%d).db
```

**Clean old events:**
```python
from src.memory.event_store import EventStore
from src.config import get_settings

settings = get_settings()
store = EventStore(settings.storage)
store.cleanup_old_snapshots()  # Deletes snapshots older than 30 days
```

### Logging

Configure logging in `config/settings.yaml`:

```yaml
logging:
  level: "DEBUG"  # DEBUG, INFO, WARNING, ERROR
  file: "data/iris.log"
  console: true
```

View logs:
```bash
tail -f data/iris.log
```

---

## Troubleshooting

### Issue: High API Costs

**Solution 1: Increase cooldown**
```yaml
monitoring:
  cooldown_seconds: 10  # Wait longer between analyses
```

**Solution 2: Reduce sensitivity**
```yaml
monitoring:
  motion_threshold: 40
  min_motion_area: 2000
```

### Issue: Missing Important Events

**Solution: Increase sensitivity**
```yaml
monitoring:
  motion_threshold: 15
  min_motion_area: 300
  cooldown_seconds: 3
```

### Issue: Poor Quality Analysis

**Solution 1: Better prompts**
Edit `config/prompts/security.txt` with more specific instructions.

**Solution 2: Higher resolution**
```yaml
camera:
  resolution: [1920, 1080]
```

**Solution 3: Better lighting**
Ensure monitored area is well-lit.

### Issue: Camera Not Found

**Windows:**
- Check Camera privacy settings
- Grant Python access to camera

**Linux:**
```bash
# Check available cameras
ls -l /dev/video*

# Add user to video group
sudo usermod -a -G video $USER
```

**macOS:**
- System Preferences → Security & Privacy → Camera
- Allow Terminal/Python
