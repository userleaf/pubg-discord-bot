import discord
from discord.ext import commands, tasks
import asyncio
import io
import sys
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Import Local Modules
import config
import database as db
import betting
import video
import utils
import os
import random

# MUST match the symbols used in your generator script
SYMBOLS = ['🍒', '🍋', '🍇', '💎', '🔔']
# ================= SETUP =================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
# ================= DIRECT API FUNCTIONS =================
# These remain normal synchronous functions
def get_account_id(player_name):
    url = f"https://api.pubg.com/shards/{config.PUBG_SHARD}/players?filter[playerNames]={player_name}"
    response = requests.get(url, headers=config.HEADERS)
    if response.status_code == 200:
        data = response.json().get('data', [])
        if data: return data[0]['id']
    return None

def get_recent_matches(account_id):
    url = f"https://api.pubg.com/shards/{config.PUBG_SHARD}/players/{account_id}"
    response = requests.get(url, headers=config.HEADERS)
    if response.status_code == 200:
        data = response.json().get('data', {})
        return [m['id'] for m in data.get('relationships', {}).get('matches', {}).get('data', [])]
    return []

def get_match_details(match_id):
    response = requests.get(f"https://api.pubg.com/shards/{config.PUBG_SHARD}/matches/{match_id}", headers=config.HEADERS)
    return response.json() if response.status_code == 200 else None

def fetch_telemetry(url):
    if not url: return None
    return requests.get(url, headers={"Accept-Encoding": "gzip"}).json()

# === NEW HELPER: Runs blocking downloads in a background thread ===
async def run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)

# ================= MATCH LOGIC =================
async def process_match(match_id, force_db_update=False, target_account_id=None, target_player_name=None):
    # REMOVED the check that prevents re-processing so !refresh works
    # if force_db_update and db.is_match_processed(match_id): force_db_update = False
    
    # === CHANGED: Use await run_blocking() to prevent freezing ===
    m_data = await run_blocking(get_match_details, match_id)
    if not m_data: return None

    # URL Check
    assets = m_data['data']['relationships'].get('assets', {}).get('data', [])
    t_id = assets[0]['id'] if assets else None
    t_url = None
    for item in m_data.get('included', []):
        if item.get('type') == 'asset' and item.get('id') == t_id:
            t_url = item.get('attributes', {}).get('url') or item.get('attributes', {}).get('URL')
            break
    if not t_url: return None

    # Identify Squad
    if target_player_name:
        for item in m_data.get('included', []):
            if item.get('type') == 'participant' and item.get('attributes', {}).get('stats', {}).get('name') == target_player_name:
                target_account_id = item.get('attributes', {}).get('stats', {}).get('playerId')
                break
    
    if not target_account_id:
        conn = db.get_connection()
        registered_ids = [r[0] for r in conn.execute("SELECT account_id FROM players").fetchall()]
        conn.close()
        for item in m_data.get('included', []):
            if item.get('type') == 'participant':
                pid = item.get('attributes', {}).get('stats', {}).get('playerId')
                if pid in registered_ids:
                    target_account_id = pid
                    break
    if not target_account_id: return None

    # Find Roster
    target_participant_id = None
    for item in m_data.get('included', []):
        if item.get('type') == 'participant' and item.get('attributes', {}).get('stats', {}).get('playerId') == target_account_id:
            target_participant_id = item.get('id')
            break
            
    target_roster_ids = []
    if target_participant_id:
        for item in m_data.get('included', []):
            if item.get('type') == 'roster':
                p_ids = [x['id'] for x in item.get('relationships', {}).get('participants', {}).get('data', [])]
                if target_participant_id in p_ids:
                    target_roster_ids = p_ids
                    break
    if not target_roster_ids: target_roster_ids = [target_participant_id] if target_participant_id else []

    clan_participants = []
    for item in m_data.get('included', []):
        if item.get('type') == 'participant' and item.get('id') in target_roster_ids:
            stats = item.get('attributes', {}).get('stats', {})
            clan_participants.append({'name': stats.get('name'), 'id': stats.get('playerId'), 'stats': stats})

    # === CHANGED: Use await run_blocking() to prevent freezing ===
    telemetry = await run_blocking(fetch_telemetry, t_url)
    
    trackers = {p['name']: {'blue_magnet':0, 'grenadier':0, 'undying':0, 'grave_robber':0, 'door_dasher':0, 'hoarder':0, 'shots_fired':0, 'shots_hit':0, 'leg_hits':0, 'snake_dist':0, 'traitor_dmg':0, 'masochist_dmg':0, 'sponge_dmg':0, 'junkie_boosts':0, 'boxer_dmg':0, 'vandal_tires':0, 'knocks_taken':0, 'thirst_dmg':0, 'killed_by_bot':False, 'weapon_stats': {}} for p in clan_participants}
    
    # Telemetry Loop
    for event in telemetry:
        etype = event.get('_T')
        attacker = (event.get('attacker') or {}).get('name')
        victim = (event.get('victim') or {}).get('name')

        if etype == 'LogPlayerAttack' and attacker in trackers:
            trackers[attacker]['shots_fired'] += 1
            w_id = (event.get('weapon') or {}).get('itemId', 'Unknown')
            if w_id not in trackers[attacker]['weapon_stats']: trackers[attacker]['weapon_stats'][w_id] = {'fired':0, 'hit':0}
            trackers[attacker]['weapon_stats'][w_id]['fired'] += 1

        if etype == 'LogPlayerTakeDamage':
            dmg = event.get('damage', 0)
            if attacker in trackers and victim in trackers:
                if attacker == victim: trackers[attacker]['masochist_dmg'] += dmg
                else: trackers[attacker]['traitor_dmg'] += dmg
            if victim in trackers:
                if event.get('damageTypeCategory') == 'Damage_BlueZone': trackers[victim]['blue_magnet'] += dmg
                trackers[victim]['sponge_dmg'] += dmg
            if attacker in trackers and attacker != victim:
                trackers[attacker]['shots_hit'] += 1
                if event.get('damageReason') in ['Leg', 'Pelvis']: trackers[attacker]['leg_hits'] += 1
                
        if etype == 'LogPlayerKill':
            killer_id = (event.get('killer') or {}).get('accountId')
            if victim in trackers and killer_id and killer_id.startswith('ai.'): trackers[victim]['killed_by_bot'] = True
        
        if etype == 'LogPlayerMakeGroggy' and victim in trackers: trackers[victim]['knocks_taken'] += 1
        if etype == 'LogItemPickup' and (event.get('character') or {}).get('name') in trackers: trackers[(event.get('character') or {}).get('name')]['hoarder'] += 1
        if etype == 'LogWheelDestroy':
             att = (event.get('attacker') or {}).get('name')
             if att in trackers: trackers[att]['vandal_tires'] += 1
        if etype == 'LogItemUse' and (event.get('character') or {}).get('name') in trackers:
             u = (event.get('character') or {}).get('name')
             i = (event.get('item') or {}).get('itemId', '')
             if any(x in i for x in ['Grenade', 'Molotov']): trackers[u]['grenadier'] += 1
             if any(x in i for x in ['FirstAid', 'MedKit']): trackers[u]['undying'] += 75
             if any(x in i for x in ['Drink', 'Painkiller']): trackers[u]['junkie_boosts'] += 1

    if force_db_update:
        stats_to_save = {}
        for p in clan_participants:
            name = p['name']
            t = trackers[name]
            s = p['stats']
            stats_to_save[name] = {
                'kills': s.get('kills', 0),
                'team_kills': 1 if t['traitor_dmg'] > 50 else 0,
                'self_damage': int(t['masochist_dmg']),
                'blue_damage': int(t['blue_magnet']),
                'distance_driven': int(s.get('rideDistance', 0)),
                'revives': s.get('revives', 0),
                'bot_deaths': 1 if t['killed_by_bot'] else 0,
                'headshots': s.get('headshotKills', 0),
                'damage_dealt': int(s.get('damageDealt', 0))
            }
        match_date = m_data['data']['attributes'].get('createdAt')
        db.save_match_stats(match_id, match_date, stats_to_save)
        db.mark_match_processed(match_id)

    return {'map': m_data['data']['attributes'].get('mapName'), 'date': m_data['data']['attributes'].get('createdAt'), 'participants': clan_participants, 'trackers': trackers}

async def resolve_bets(data, match_id):
    active_bets = db.get_active_bets()
    if not active_bets: return None

    # Map player name to their damage in this match
    dmg_map = {p['name']: int(p['stats'].get('damageDealt', 0)) for p in data['participants']}

    rank = 99
    for p in data['participants']:
        r = p['stats'].get('winPlace', 99)
        if r < rank: rank = r
    
    sorted_dmg = sorted(data['participants'], key=lambda x: x['stats'].get('damageDealt', 0), reverse=True)
    most_dmg_name = sorted_dmg[0]['name'] if sorted_dmg else "None"

    sorted_death = sorted(data['participants'], key=lambda x: x['stats'].get('timeSurvived', 9999))
    first_die_name = sorted_death[0]['name'] if sorted_death else "None"

    payouts = []
    for bet_id, uid, btype, target, amt in active_bets:
        winnings = 0
        won = False
        refund = False
        target_clean = target.lower() if target else ""
        
        if btype == "WIN" and rank == 1: winnings, won = amt * 10, True
        elif btype == "TOP10" and rank <= 10: winnings, won = amt * 2, True
        elif btype == "MOST_DMG" and target_clean == most_dmg_name.lower(): winnings, won = amt * 3, True
        elif btype == "FIRST_DIE" and target_clean == first_die_name.lower(): winnings, won = amt * 3, True
        
        # === DUEL LOGIC ===
        elif btype.startswith("DUEL"):
            try:
                # Format: "DUEL (2.5x)"
                odds = float(btype.split('(')[1].split('x')[0])
                # Target: "vs OpponentName"
                opp_name = target.replace("vs ", "")
                
                bettor_info = db.get_player_by_discord_id(uid)
                bettor_name = bettor_info[0] if bettor_info else None
                
                if bettor_name in dmg_map and opp_name in dmg_map:
                    my_dmg = dmg_map[bettor_name]
                    opp_dmg = dmg_map[opp_name]
                    if my_dmg > opp_dmg:
                        winnings = int(amt * odds)
                        won = True
                else:
                    refund = True
            except:
                refund = True

        if refund:
            db.update_balance(uid, amt)
            payouts.append(f"↩️ <@{uid}> refunded **{amt}** (Player missing)")
        elif won:
            db.update_balance(uid, winnings)
            payouts.append(f"💸 <@{uid}> won **{winnings}**! ({btype})")

    db.clear_active_bets()
    
    embed = discord.Embed(title="🎰 Casino Payouts", color=0x2ecc71)
    embed.description = "\n".join(payouts) if payouts else "💀 **No winners.** House wins."
    embed.set_footer(text=f"Result: #{rank} | Dmg: {most_dmg_name} | Died: {first_die_name}")
    return embed

async def close_betting_logic(bot_instance):
    db.set_game_state("betting_status", "LOCKED")
    
    channel_id = db.get_game_state('betting_channel')
    if not channel_id: return

    bets = db.get_active_bets()
    embed = discord.Embed(title="🔒 Betting Closed", description="Bets are locked! Summary:", color=0xe74c3c)
    
    if bets:
        bet_lines = ""
        for _, uid, btype, target, amt in bets:
            target_display = f" ({target})" if target and target != "Squad" else ""
            bet_lines += f"• <@{uid}>: **{amt}** on **{btype}**{target_display}\n"
        embed.add_field(name="📋 Current Bets", value=bet_lines, inline=False)
    else:
        embed.add_field(name="📋 Current Bets", value="No bets were placed.", inline=False)
    
    channel = bot_instance.get_channel(int(channel_id))
    if channel: await channel.send(embed=embed)


class CasinoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @discord.ui.button(label="🎰 SPIN (100c)", style=discord.ButtonStyle.success, custom_id="casino_spin_btn")
    async def spin_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        # 1. Money Check
        if db.get_balance(user_id) < 100:
            return await interaction.response.send_message("❌ **Insufficient funds!**", ephemeral=True)
        db.update_balance(user_id, -100)
        
        # 2. Calculate Result
        s1 = random.choice(SYMBOLS)
        s2 = random.choice(SYMBOLS)
        s3 = random.choice(SYMBOLS)
        
        # 3. File Paths
        filename_base = f"{s1}_{s2}_{s3}"
        gif_path = os.path.join("slot_gifs", f"{filename_base}.gif")
        png_path = os.path.join("slot_gifs", f"{filename_base}.png")
        
        # 4. Send GIF (Animation)
        if os.path.exists(gif_path):
            file = discord.File(gif_path, filename="spin.gif")
            await interaction.response.send_message(content="🎰 **Spinning...**", file=file, ephemeral=True)
        else:
            await interaction.response.send_message(content="❌ Error: Missing assets.", ephemeral=True)
            return

        # 5. Wait for Animation (2.5 seconds)
        # This covers the spin time + part of the "pause" at the end of the GIF
        await asyncio.sleep(2.5)
        
        # 6. Calculate Winnings Text
        winnings = 0
        status_text = "Better luck next time."
        
        if s1 == s2 == s3:
            if s1 == '🔔': 
                winnings = 5000
                status_text = "🚨 **JACKPOT!** (+5000)"
            else: 
                winnings = 1000
                status_text = "🏆 **TRIPLE!** (+1000)"
        elif s1 == s2 or s2 == s3 or s1 == s3:
            winnings = 200
            status_text = "✨ **PAIR!** (+200)"

        if winnings > 0:
            db.update_balance(user_id, winnings)

        # 7. THE SWAP (GIF -> PNG)
        # We upload the PNG and replace the message attachments
        if os.path.exists(png_path):
            new_file = discord.File(png_path, filename="result.png")
            
            # Edit the ORIGINAL message:
            # - Update text to show result
            # - Replace GIF with PNG
            await interaction.edit_original_response(
                content=f"🎰 **RESULT:**\n{status_text}", 
                attachments=[new_file]
            )

# ================= EVENTS & TASKS =================
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    db.init_db()
    bot.add_view(CasinoView())
    if not auto_match_checker.is_running(): auto_match_checker.start()


@tasks.loop(minutes=config.CFG_MINUTES)
async def auto_match_checker():
    # 1. GATHER CANDIDATES (Like the old code)
    players = db.get_all_players()
    candidate_matches = []
    
    # Check what sessions are waiting for results
    # Returns (session_id, start_time_string)
    waiting_session = db.get_oldest_unresolved_session() 

    for (did, acc_id, name) in players:
        # Get last 3 matches for every player
        recent = await run_blocking(get_recent_matches, acc_id)
        for m in recent[:3]:
            if not db.is_match_processed(m):
                # Fetch details to get the TIME
                m_details = await run_blocking(get_match_details, m)
                if not m_details: continue
                
                created_at_str = m_details['data']['attributes']['createdAt']
                m_time = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ")
                
                # Add to list: (Time, MatchID, AccountID)
                candidate_matches.append((m_time, m, acc_id))

    # 2. SORT BY TIME (Oldest match first)
    # This ensures we process history linearly
    candidate_matches.sort(key=lambda x: x[0])

    # 3. ANALYZE MATCHES
    for (m_time, mid, acc_id) in candidate_matches:
        # Double check it wasn't processed in a previous loop iteration
        if db.is_match_processed(mid): continue
        
        # --- LOGIC: IS THIS A BETTING MATCH? ---
        is_betting_match = False
        
        if waiting_session:
            session_id = waiting_session[0]
            session_start_str = waiting_session[1]
            session_start = datetime.strptime(session_start_str, "%Y-%m-%d %H:%M:%S.%f")
            
            # TIME CHECK:
            # 1. If match is OLDER than session start (-15 min buffer): 
            #    It is an old game. Ignore for betting. Just save stats.
            # 2. If match is NEWER than session start:
            #    This is the game we are waiting for!
            
            if m_time < (session_start - timedelta(minutes=15)):
                # Match happened BEFORE bets opened.
                print(f"⚠️ Skipping Old Match {mid} (Too early for Session #{session_id})")
                # We still process it below for stats, but is_betting_match stays False
            else:
                # Match happened AFTER bets opened.
                is_betting_match = True
                print(f"💰 Betting Match Found for Session #{session_id}: {mid}")

        # --- PROCESS THE MATCH ---
        print(f"🔄 Analyzing {mid}...")
        data = await process_match(mid, force_db_update=True, target_account_id=acc_id)
        
        # Mark processed immediately so we don't re-run it
        db.mark_match_processed(mid)

        # --- RESOLVE BETS (If applicable) ---
        if is_betting_match and data and waiting_session:
            session_id = waiting_session[0]
            
            print(f"💰 Payout Triggered for Session #{session_id}...")
            payout_embed = await resolve_bets_for_session(data, session_id)
            
            # Post Result
            channel_id = db.get_game_state('latest_betting_channel') or config.MAIN_CHANNEL_ID
            channel = bot.get_channel(int(channel_id))
            if channel: 
                await channel.send(f"🔔 **Results for Round #{session_id}**", embed=payout_embed)
            
            # CLOSE THE SESSION PERMANENTLY
            db.close_session(session_id, match_id=mid, status="RESOLVED")
            
            # Refresh waiting_session variable in case there is ANOTHER session waiting for the next match
            waiting_session = db.get_oldest_unresolved_session()

# ================= COMMANDS =================
@bot.command()
async def register(ctx, pubg_name: str):
    acc_id = await run_blocking(get_account_id, pubg_name)
    if acc_id:
        db.register_user(ctx.author.id, pubg_name, acc_id)
        db.update_balance(ctx.author.id, 0)
        await ctx.send(f"✅ **{pubg_name}** linked!")
    else:
        await ctx.send("❌ Player not found.")

@bot.command()
async def balance(ctx):
    bal = db.get_balance(ctx.author.id)
    await ctx.send(f"💰 **{ctx.author.display_name}**: {bal} coins")

@bot.command()
async def daily(ctx):
    user_id = ctx.author.id
    
    # 1. Check Availability (Midnight Reset)
    if not db.check_daily_available(user_id):
        # Calculate time until midnight
        now = datetime.now()
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        remaining = tomorrow - now
        h, r = divmod(int(remaining.total_seconds()), 3600)
        m, _ = divmod(r, 60)
        return await ctx.send(f"⏳ **Already claimed today.**\nNext reward in: **{h}h {m}m** (Midnight).")

    # 2. Calculate Bonus based on Performance
    base_reward = 100
    bonus = 0
    avg_dmg = 0
    
    # Get player name to look up stats
    player_data = db.get_player_by_discord_id(user_id) # returns (name, account_id)
    
    if player_data:
        name = player_data[0]
        avg_dmg = db.get_player_avg_damage(name, limit=10)
        
        # LOGIC: 50% of Average Damage, Capped at 200
        # Example: 400 dmg -> 200 bonus
        # Example: 100 dmg -> 50 bonus
        bonus = int(avg_dmg * 0.5)
        if bonus > 200: bonus = 200
    
    total_reward = base_reward + bonus
    
    # 3. Pay the user
    db.update_balance(user_id, total_reward)
    
    # 4. Update "Last Daily" timestamp to NOW
    conn = db.get_connection()
    conn.execute("UPDATE wallets SET last_daily = ? WHERE discord_id = ?", (datetime.now(), user_id))
    conn.commit()
    conn.close()
    
    # 5. Send Message
    embed = discord.Embed(title="💰 Daily Reward", color=0x2ecc71)
    embed.add_field(name="Base Reward", value=f"**{base_reward}** coins")
    
    if bonus > 0:
        embed.add_field(name="Performance Bonus", value=f"**+{bonus}** coins\n*(Avg Dmg: {avg_dmg})*")
    else:
        embed.add_field(name="Performance Bonus", value="0 coins\n*(Play matches to increase this!)*")
        
    embed.set_footer(text=f"Total: +{total_reward} coins added to wallet.")
    await ctx.send(embed=embed)

@bot.command()
async def startbets(ctx):
    """Starts a NEW betting session (supports multiple active games)"""
    
    # 1. Create a new Session in DB
    session_id = db.create_betting_session()
    
    # 2. Set the 'channel' state so we know where to post results for THIS session
    # We can store this in game_state just for the "latest" channel
    db.set_game_state("latest_betting_channel", ctx.channel.id)

    embed = discord.Embed(title=f"🎰 Bets Open (Round #{session_id})", description="**New match starting!**\nPlace your bets now.", color=0xf1c40f)
    embed.add_field(name="Multi-Game Support", value="You can bet on this game even if the previous one hasn't finished!")
    
    # Pass the session_id to the View so the buttons know which bucket to put money in
    await ctx.send(embed=embed, view=betting.BettingView(session_id=session_id))
    
    # Auto-lock after 5 minutes
    await asyncio.sleep(300)
    
    # Check if THIS specific session is still open
    conn = db.get_connection()
    status = conn.execute("SELECT status FROM betting_sessions WHERE session_id=?", (session_id,)).fetchone()
    conn.close()
    
    if status and status[0] == 'OPEN':
        db.close_session(session_id, status="LOCKED")
        await ctx.send(f"🔒 **Bets Closed for Round #{session_id}!**\nWaiting for match results...")

@bot.command()
async def stopbets(ctx):
    if db.get_game_state('betting_status') == "OPEN":
        await close_betting_logic(bot)
    else:
        await ctx.send("❌ No bets open.")

@bot.command()
async def report(ctx, username: str = None):
    status = await ctx.send("📝 **Fetching Report...**")
    target_name, target_id = username, None
    if username:
        local = db.get_player_by_name_fuzzy(username)
        if local: target_name, target_id = local
        else: target_id = await run_blocking(get_account_id, username)
        if not target_id: return await status.edit(content=f"❌ Player `{username}` not found.")
    else:
        user = db.get_player_by_discord_id(ctx.author.id)
        if not user: return await status.edit(content="❌ Register first!")
        target_name, target_id = user[0], user[1]

    matches = await run_blocking(get_recent_matches, target_id)
    data = None
    for mid in matches[:5]:
        save = True if not username else False 
        data = await process_match(mid, force_db_update=save, target_account_id=target_id)
        if data: break
        
    if data:
        summary, highlights, rank = utils.calculate_highlights_and_summary(data)
        embed = discord.Embed(title=f"Match Report: {data['map']}", description=f"📅 {data['date']}", color=0xffa500)
        desc = ""
        for s in summary: desc += f"**{s['name']}**: {s['kills']} ☠️ | {s['dmg']} 💥\n"
        embed.add_field(name="📊 Squad Summary", value=desc, inline=False)
        txt = ""
        for h in highlights: txt += f"{config.FACT_DEFINITIONS[h['type']]['title']} **{h['player']}** — {config.FACT_DEFINITIONS[h['type']]['format'].format(h['value'])}\n"
        embed.add_field(name="🏆 Highlights", value=txt or "Normal Game.", inline=False)
        await status.delete()
        await ctx.send(embed=embed)
    else:
        await status.edit(content="❌ No valid match found.")

@bot.command()
async def video(ctx):
    status = await ctx.send("🎬 **Generating Video...**")
    user = db.get_player_by_discord_id(ctx.author.id)
    if not user: return await status.edit(content="❌ Register first!")
    matches = await run_blocking(get_recent_matches, user[1])
    data = None
    for mid in matches[:5]:
        data = await process_match(mid, target_account_id=user[1])
        if data: break
    if data:
        summary, highlights, rank = utils.calculate_highlights_and_summary(data)
        path = await run_blocking(video.generate_video_report, summary, highlights, rank, data['map'])
        if path:
            await status.delete()
            await ctx.send(file=discord.File(path))
        else:
            await status.edit(content="❌ Video template missing.")
    else:
        await status.edit(content="❌ No valid match found.")

@bot.command()
async def trend(ctx):
    user = db.get_player_by_discord_id(ctx.author.id)
    if not user: return await ctx.send("❌ Register first!")
    status = await ctx.send("📈 **Generating Trend...**")
    matches = await run_blocking(get_recent_matches, user[1])
    kills, dmg = [], []
    for mid in matches[:10]:
        m = await run_blocking(get_match_details, mid)
        if not m: continue
        for i in m.get('included', []):
            if i.get('type') == 'participant' and i.get('attributes', {}).get('stats', {}).get('playerId') == user[1]:
                s = i['attributes']['stats']
                kills.append(s.get('kills', 0))
                dmg.append(s.get('damageDealt', 0))
                break
    kills.reverse(); dmg.reverse()
    
    # Matplotlib must run in thread too
    def create_plot():
        fig, ax1 = plt.subplots()
        color = 'tab:red'
        ax1.set_xlabel('Matches')
        ax1.set_ylabel('Damage', color=color)
        ax1.plot(dmg, color=color, marker='o'); ax1.tick_params(axis='y', labelcolor=color)
        ax2 = ax1.twinx()
        color = 'tab:blue'
        ax2.set_ylabel('Kills', color=color)
        ax2.plot(kills, color=color, marker='x', linestyle='--'); ax2.tick_params(axis='y', labelcolor=color)
        plt.title(f"Trend: {user[0]}")
        fig.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        return buf

    buf = await run_blocking(create_plot)
    await status.delete()
    await ctx.send(file=discord.File(buf, 'trend.png'))

@bot.command()
async def leaderboard(ctx):
    conn = db.get_connection()
    c = conn.cursor()
    embed = discord.Embed(title="🏆 Weekly Leaderboard", color=0xd4af37)
    seven_days_ago = datetime.now() - timedelta(days=7)
    has_data = False
    for key, (title, unit) in config.LEADERBOARD_CONFIG.items():
        row = c.execute("SELECT pubg_name, SUM(value) as total FROM match_stats WHERE stat_key=? AND match_date > ? GROUP BY pubg_name ORDER BY total DESC LIMIT 1", (key, seven_days_ago)).fetchone()
        if row and row[1] > 0:
            has_data = True
            val_fmt = f"{int(row[1]/1000)}km" if key == 'distance_driven' else row[1]
            embed.add_field(name=f"🏅 {title}", value=f"**{row[0]}**\n{val_fmt} {unit}")
    conn.close()
    await ctx.send(embed=embed if has_data else "❌ No stats in last 7 days.")

@bot.command()
async def clan(ctx):
    conn = db.get_connection()
    players = conn.execute("SELECT pubg_name FROM players").fetchall()
    conn.close()
    await ctx.send("**📋 Clan Members:**\n" + "\n".join([f"• {p[0]}" for p in players]) if players else "No members.")

@bot.command()
async def gun(ctx):
    user = db.get_player_by_discord_id(ctx.author.id)
    if not user: return await ctx.send("❌ Register first!")
    status = await ctx.send("🔫 **Analyzing...**")
    matches = await run_blocking(get_recent_matches, user[1])
    data = None
    for mid in matches[:5]:
        data = await process_match(mid, target_account_id=user[1])
        if data: break
    if not data: return await status.edit(content="❌ No valid data.")
    stats = data['trackers'].get(user[0], {}).get('weapon_stats', {})
    desc = "\n".join([f"**{k.replace('Item_Weapon_', '').replace('_C', '')}**: {v['fired']} shots" for k, v in stats.items()])
    await status.delete()
    await ctx.send(embed=discord.Embed(title=f"🔫 Gun Stats: {user[0]}", description=desc or "No shots fired.", color=0x3498db))

@bot.command()
async def refresh(ctx):
    status = await ctx.send("🔄 **Force Refreshing All Stats...** (This will take a moment)")
    players = db.get_all_players()
    count = 0
    for (did, acc_id, name) in players:
        # Scan last 15 matches to safely backfill damage stats
        matches = await run_blocking(get_recent_matches, acc_id)
        for m in matches[:15]:
            # Always process regardless of DB state to fill missing damage data
            await process_match(m, force_db_update=True, target_account_id=acc_id)
            count += 1
            
    await status.edit(content=f"✅ **Damage Data Restored!** Rescanned {count} matches.")

@bot.command(name="break")
async def break_time(ctx, minutes: int):
    """Usage: !break 5 (Sets a 5 minute timer)"""
    
    # 1. Calculate End Time
    now = datetime.now()
    end_time = now + timedelta(minutes=minutes)
    time_str = end_time.strftime("%H:%M")
    
    # 2. Send Start Message
    print(f"⏱️ Break started for {minutes} minutes.")
    await ctx.send(f"☕ **Break Started!**\nWe will be back in **{minutes} minutes** (at {time_str}).")
    
    # 3. The Wait (Non-blocking)
    # The bot stays awake and listens to other commands while this runs in background
    await asyncio.sleep(minutes * 60)
    
    # 4. Send End Message
    # We use @here to alert everyone online
    print("🔔 Break is over!")
    try:
        await ctx.send(f"🔔 **BREAK OVER!**\n@here Let's get back to the game!") 
    except Exception as e:
        print(f"⚠️ Error sending break message: {e}")
        # Fallback if pinging fails
        await ctx.send("🔔 **BREAK OVER!** (Time is up)")

@bot.command()
async def casino(ctx):
    # Spawn the persistent Arcade Machine
    embed = discord.Embed(title="🎰 CLAN CASINO", description="Press the button to play!\n**Cost:** 100 coins\n\n**Payouts:**\n🔔🔔🔔 = **5000**\n🍒🍒🍒 = **1000**\n🍒🍒❓ = **200**", color=0xf1c40f)
    await ctx.send(embed=embed, view=CasinoView())

# ================= ADMIN COMMANDS =================

def is_admin(ctx):
    # DEBUG PRINT: This will show up in your terminal every time you run an admin command
    print(f"DEBUG: Command by {ctx.author.name} (ID: {ctx.author.id})")
    print(f"DEBUG: Checking against Config ID: {config.ADMIN_ID}")
    
    # Check ID match
    if ctx.author.id == config.ADMIN_ID:
        return True
    
    # Fallback: Check Name match (legacy support)
    # This handles both "Display Name" and "Username"
    if ctx.author.name == "Usemaki06" or ctx.author.display_name == "Usemaki06":
        return True
        
    return False

@bot.command()
@commands.check(is_admin)
async def gift(ctx, target: str, amount: int, *, message: str = "Bonus!"):
    """
    Usage (in DM or Chat): !gift #all 100 Happy Monday!
    """
    
    # 1. Determine where to send the announcement
    if ctx.guild is None:
        # If command came from DM, send result to the Main Channel
        channel = bot.get_channel(config.MAIN_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ Error: I can't find the main channel ID set in config.")
            return
    else:
        # If command came from a server, send result to that same channel
        channel = ctx.channel
        # Optional: Try to delete the command message if in server
        try: await ctx.message.delete()
        except: pass

    # 2. Logic (Same as before)
    print(f"🎁 Gift triggered by {ctx.author.name}") 
    
    if target == "#all":
        players = db.get_all_players()
        count = 0
        for (did, _, _) in players:
            db.update_balance(did, amount)
            count += 1
        
        embed = discord.Embed(title="🎁 CLAN GIFT", description=f"**{ctx.author.display_name}** sent **{amount}** coins to everyone!", color=0xe91e63)
        embed.add_field(name="Message", value=message)
        embed.set_footer(text=f"Sent to {count} members.")
        
        # SEND TO THE CHANNEL
        await channel.send(embed=embed)
        # Reply to Admin in DM confirming it worked
        if ctx.guild is None:
            await ctx.send(f"✅ Posted gift to #{channel.name}")

    else:
        # Single User Logic
        conn = db.get_connection()
        try:
            converter = commands.MemberConverter()
            member = await converter.convert(ctx, target) # This might fail in DMs if bot doesn't share server
            cursor = conn.execute("SELECT discord_id FROM players WHERE discord_id=?", (member.id,))
        except:
            cursor = conn.execute("SELECT discord_id FROM players WHERE pubg_name LIKE ?", (f"%{target}%",))
            
        row = cursor.fetchone()
        conn.close()
        
        if row:
            uid = row[0]
            db.update_balance(uid, amount)
            
            # Construct the public message
            # We fetch the Discord User object to tag them properly in the announcement
            try:
                receiver = await bot.fetch_user(uid)
                receiver_tag = receiver.mention
            except:
                receiver_tag = target

            await channel.send(f"🎁 **{ctx.author.display_name}** sent **{amount}** coins to {receiver_tag}.\n📝 *{message}*")
            
            if ctx.guild is None:
                await ctx.send(f"✅ Sent {amount} to {target} in #{channel.name}")
        else:
            await ctx.send(f"❌ Could not find user `{target}`.")

@bot.command()
@commands.check(is_admin)
async def freespin(ctx):
    """!freespin - Gives 100 coins to everyone"""
    print(f"🎰 Freespin triggered by {ctx.author.name}") # Debug output
    players = db.get_all_players()
    for (did, _, _) in players:
        db.update_balance(did, 100)
    
    embed = discord.Embed(title="🎰 FREE SPIN ON THE HOUSE!", color=0xf1c40f)
    embed.description = f"**{ctx.author.display_name}** just credited everyone **100 coins**!\nGo play the casino right now!"
    await ctx.send(embed=embed)

@bot.command()
@commands.check(is_admin)
async def balances(ctx):
    """!balances - Show leaderboard"""
    print(f"💰 Balances triggered by {ctx.author.name}") # Debug output
    conn = db.get_connection()
    query = """
    SELECT p.pubg_name, w.balance 
    FROM wallets w 
    JOIN players p ON w.discord_id = p.discord_id 
    ORDER BY w.balance DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        return await ctx.send("❌ No balances found.")

    desc = ""
    total = 0
    for idx, (name, bal) in enumerate(rows, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"**{idx}.**"
        desc += f"{medal} **{name}**: {bal}\n"
        total += bal

    embed = discord.Embed(title="💰 Clan Treasury", description=desc, color=0x3498db)
    embed.set_footer(text=f"Total Economy: {total}")
    await ctx.send(embed=embed)

# GLOBAL ERROR HANDLER FOR ADMIN CHECKS
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        # This catches the 'is_admin' failure
        print(f"⛔ Access Denied for {ctx.author.name}")
        await ctx.send("⛔ **Admin Only.** You are not authorized.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument! Usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    else:
        # Print other errors to terminal so we see them
        print(f"⚠️ Error: {error}")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    bot.run(config.DISCORD_TOKEN)