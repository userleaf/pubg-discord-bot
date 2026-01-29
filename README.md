# 🎰 PUBG Clan Tracker & Betting Bot

A Discord bot that tracks PUBG stats, generates video highlight reels, and features a full-fledged virtual betting economy for your clan.

## ✨ Features

* **📊 Automatic Tracking:** Silently monitors clan matches in the background (every 2 minutes) and updates stats automatically.
* **💰 Virtual Economy:** Complete betting system. Bet virtual coins on who wins, dies first, or deals the most damage in the next match.
* **🎬 Highlight Generator:** Generates a 30-second video (`.mp4`) summary of the last match with stats overlays.
* **📈 Trend Analysis:** Visualizes K/D and Damage trends over the last 10 games with generated graphs.
* **🏆 Weekly Leaderboard:** Tracks specific titles like "Uber Driver" (Distance), "Bot Food" (AI Deaths), "Sniper," and more.
* **🔫 Gun Analysis:** Detailed breakdown of weapon accuracy and usage for your recent matches.

## 🚀 Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/userleaf/pubg-clan-bot.git
cd pubg-clan-bot
```

### 2. Install Dependencies
Ensure you have Python 3.8+ installed.
```bash
pip install -r requirements.txt
```
*Note: This bot requires `ffmpeg` installed on your system for video generation (MoviePy).*

### 3. Configure Secrets (Important!)
Create a file named `.env` in the root directory. **Do not upload this file.**
Paste your keys inside:

```ini
DISCORD_TOKEN="your_discord_bot_token"
PUBG_API_KEY="your_pubg_api_key"
PUBG_SHARD="steam"
```

### 4. Media Assets
Place your video template file named `video.mp4` (approx 30s long) in the root folder. The bot uses this as the background for the highlight reel. You also need a font file (e.g., `arialbd.ttf`) if you want custom fonts, otherwise it defaults.

### 5. Run the Bot
```bash
python main.py
```
The database (`clan.db`) will be created automatically on the first run.

## 🎮 Commands

### General
* `!register [PUBG_Name]` - Link your account and backfill last 10 games.
* `!clan` - List registered members.
* `!trend` - Show a graph of your recent performance.
* `!report` - detailed report of your last match.
* `!video` - Generate a video highlight reel.
* `!leaderboard` - Show top stats for the last 7 days.
* `!gun` - Show weapon stats for the last match.
* `!refresh` - Manually scan historic matches for all users.

### Economy & Betting
* `!balance` - Check your wallet.
* `!daily` - Claim 100 free coins (24h cooldown).
* `!startbets` - Open the betting window for the next match (Global).
* `!stopbets` - Force close betting and list active bets.

## 🛠️ Project Structure

* `main.py`: Entry point, command handlers, and betting logic.
* `pubg_api.py`: Wrappers for the PUBG API (Telemetry, Match Details).
* `database.py`: SQLite handling and state management.
* `betting.py`: Discord UI Views (Buttons/Modals) for the interaction layer.
* `video.py`: MoviePy logic for generating video reports with overlays.
* `utils.py`: Helper functions for stats calculation and summarization.
* `config.py`: Configuration loader.

## 🛡️ Security Note
This project uses a `.gitignore` to prevent `clan.db` (user data) and `.env` (API keys) from being committed to version control. Always keep your `.env` safe!