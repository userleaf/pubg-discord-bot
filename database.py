import sqlite3
from datetime import datetime
from config import LEADERBOARD_CONFIG

DB_NAME = 'clan.db'

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players (discord_id INTEGER PRIMARY KEY, pubg_name TEXT, account_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS processed_matches (match_id TEXT PRIMARY KEY, processed_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS match_stats (pubg_name TEXT, match_id TEXT, stat_key TEXT, value INTEGER, match_date TIMESTAMP, PRIMARY KEY (pubg_name, match_id, stat_key))''')
    c.execute('''CREATE TABLE IF NOT EXISTS wallets (discord_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 1000, last_daily TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS active_bets (bet_id INTEGER PRIMARY KEY AUTOINCREMENT, discord_id INTEGER, bet_type TEXT, target TEXT, amount INTEGER, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_state (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def register_user(discord_id, name, account_id):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO players (discord_id, pubg_name, account_id) VALUES (?, ?, ?)", (discord_id, name, account_id))

def get_player_by_discord_id(discord_id):
    with get_connection() as conn:
        res = conn.execute("SELECT pubg_name, account_id FROM players WHERE discord_id=?", (discord_id,)).fetchone()
    return res

def get_player_by_name_fuzzy(pubg_name):
    with get_connection() as conn:
        res = conn.execute("SELECT pubg_name, account_id FROM players WHERE pubg_name COLLATE NOCASE = ?", (pubg_name,)).fetchone()
    return res

def get_all_players():
    with get_connection() as conn:
        res = conn.execute("SELECT discord_id, account_id, pubg_name FROM players").fetchall()
    return res

def is_match_processed(match_id):
    with get_connection() as conn:
        res = conn.execute("SELECT match_id FROM processed_matches WHERE match_id=?", (match_id,)).fetchone()
    return res is not None

def mark_match_processed(match_id):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO processed_matches (match_id, processed_at) VALUES (?, ?)", (match_id, datetime.now()))

def save_match_stats(match_id, match_date_str, stats_dict):
    try: dt = datetime.strptime(match_date_str, "%Y-%m-%dT%H:%M:%SZ")
    except: dt = datetime.now()
    with get_connection() as conn:
        for name, data in stats_dict.items():
            for stat_key, value in data.items():
                if stat_key in LEADERBOARD_CONFIG:
                    conn.execute('''INSERT OR IGNORE INTO match_stats (pubg_name, match_id, stat_key, value, match_date) VALUES (?, ?, ?, ?, ?)''', (name, match_id, stat_key, value, dt))

def get_balance(discord_id):
    with get_connection() as conn:
        res = conn.execute("SELECT balance FROM wallets WHERE discord_id=?", (discord_id,)).fetchone()
    return res[0] if res else 0

def update_balance(discord_id, amount):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO wallets (discord_id, balance) VALUES (?, 1000)", (discord_id,))
        conn.execute("UPDATE wallets SET balance = balance + ? WHERE discord_id=?", (amount, discord_id))

def place_bet(discord_id, bet_type, target, amount):
    bal = get_balance(discord_id)
    if bal < amount: return False
    update_balance(discord_id, -amount)
    with get_connection() as conn:
        conn.execute("INSERT INTO active_bets (discord_id, bet_type, target, amount, created_at) VALUES (?, ?, ?, ?, ?)", 
                     (discord_id, bet_type, target, amount, datetime.now()))
    return True

def get_active_bets():
    with get_connection() as conn:
        res = conn.execute("SELECT bet_id, discord_id, bet_type, target, amount FROM active_bets").fetchall()
    return res

def clear_active_bets():
    with get_connection() as conn:
        conn.execute("DELETE FROM active_bets")

def set_game_state(key, value):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO game_state (key, value) VALUES (?, ?)", (key, str(value)))

def get_game_state(key):
    with get_connection() as conn:
        res = conn.execute("SELECT value FROM game_state WHERE key=?", (key,)).fetchone()
    return res[0] if res else None
def get_player_avg_damage(pubg_name):
    """Calculates average damage over the last 10 tracked matches."""
    with get_connection() as conn:
        # Get last 10 damage values
        rows = conn.execute('''
            SELECT value FROM match_stats 
            WHERE pubg_name=? AND stat_key='damage_dealt' 
            ORDER BY match_date DESC LIMIT 10
        ''', (pubg_name,)).fetchall()
    
    if not rows: return 0
    total = sum(r[0] for r in rows)
    return total / len(rows)