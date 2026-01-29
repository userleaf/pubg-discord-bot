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

# ================= EVENTS & TASKS =================
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    db.init_db()
    if not auto_match_checker.is_running(): auto_match_checker.start()

@tasks.loop(minutes=config.CFG_MINUTES)
async def auto_match_checker():
    print("🔄 Checking matches...")
    bet_status = db.get_game_state('betting_status')
    start_time_str = db.get_game_state('betting_start_time')
    bet_channel_id = db.get_game_state('betting_channel')
    
    bet_start_dt = None
    if start_time_str:
        try: bet_start_dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f")
        except: pass

    players = db.get_all_players()
    candidate_matches = []
    
    for (did, acc_id, name) in players:
        # ASYNC BLOCKING CALL WRAPPER NOT NEEDED HERE as getting match list is fast, 
        # but to be safe we could wrap it. For now, leave as is, the big one is telemetry.
        for m in get_recent_matches(acc_id)[:3]:
            if not db.is_match_processed(m):
                m_details = await run_blocking(get_match_details, m)
                if not m_details: continue
                created_at_str = m_details['data']['attributes']['createdAt']
                created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ")
                candidate_matches.append((created_at, m, acc_id))

    candidate_matches.sort(key=lambda x: x[0])

    for (m_time, mid, acc_id) in candidate_matches:
        if db.is_match_processed(mid): continue
        
        is_betting_match = False
        if bet_status == "LOCKED" and bet_start_dt:
            if m_time > bet_start_dt:
                is_betting_match = True
                print(f"💰 Betting Match Found: {mid}")
            else:
                print(f"⚠️ Skipping old match {mid}")
                db.mark_match_processed(mid)
                continue

        print(f"🔄 Analyzing {mid}...")
        data = await process_match(mid, force_db_update=True, target_account_id=acc_id)
        db.mark_match_processed(mid)

        if is_betting_match and data:
            print("💰 Resolving Bets...")
            payout_embed = await resolve_bets(data, mid)
            if payout_embed and bet_channel_id:
                channel = bot.get_channel(int(bet_channel_id))
                if channel: await channel.send(embed=payout_embed)
            db.set_game_state("betting_status", "CLOSED")
            break

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
    conn = db.get_connection()
    row = conn.execute("SELECT last_daily FROM wallets WHERE discord_id=?", (user_id,)).fetchone()
    now = datetime.now()
    if row and row[0]:
        try:
            last = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f")
            delta = now - last
            if delta < timedelta(hours=24):
                wait = timedelta(hours=24) - delta
                h, r = divmod(int(wait.total_seconds()), 3600)
                m, _ = divmod(r, 60)
                await ctx.send(f"⏳ Wait **{h}h {m}m**.")
                conn.close()
                return
        except: pass
    db.update_balance(user_id, 100)
    conn.execute("UPDATE wallets SET last_daily = ? WHERE discord_id = ?", (now, user_id))
    conn.commit()
    conn.close()
    await ctx.send(f"💰 **Cha-ching!** +100 coins.")

@bot.command()
async def startbets(ctx):
    db.set_game_state("betting_status", "OPEN")
    db.set_game_state("betting_channel", ctx.channel.id)
    db.set_game_state("betting_start_time", datetime.utcnow())
    db.clear_active_bets()
    
    embed = discord.Embed(title="🎰 Place Your Bets!", description="Betting is OPEN for the next match.\n\n🍗 **Win:** 10x\n🔟 **Top 10:** 2x\n💀 **First Die:** 3x\n💥 **Most Dmg:** 3x\n⚔️ **Duel:** vs Player", color=0xf1c40f)
    await ctx.send(embed=embed, view=betting.BettingView())
    
    await asyncio.sleep(300)
    if db.get_game_state('betting_status') == "OPEN":
        await close_betting_logic(bot)

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

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    bot.run(config.DISCORD_TOKEN)