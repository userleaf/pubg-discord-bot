import discord # type: ignore
from discord.ui import Button, View, Modal, TextInput, Select # type: ignore
import database as db
import math

class PvPOpponentSelectView(View):
    def __init__(self, bettor_name, bettor_id):
        super().__init__()
        self.bettor_name = bettor_name
        self.bettor_id = bettor_id
        
        # Get all players to list as opponents
        import database as db # Late import to avoid circular dep issues
        conn = db.get_connection()
        players = [r[0] for r in conn.execute("SELECT pubg_name FROM players WHERE pubg_name != ?", (bettor_name,)).fetchall()]
        conn.close()

        options = [discord.SelectOption(label=p, description="Duel this player") for p in players[:25]]
        if not options:
            options = [discord.SelectOption(label="No opponents found", description="Register more players")]

        select = Select(placeholder="⚔️ Choose your opponent...", options=options)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        opponent = interaction.data['values'][0]
        
        # --- ODDS CALCULATION LOGIC ---
        import database as db
        my_avg = db.get_player_avg_damage(self.bettor_name)
        opp_avg = db.get_player_avg_damage(opponent)
        
        # Prevent division by zero / low stats
        if my_avg < 10: my_avg = 100 
        if opp_avg < 10: opp_avg = 100

        # Formula: Payout = 1 + (Opponent / Me)
        # If I am bad (100) and Opp is good (200), Payout = 1 + (200/100) = 3.0x
        ratio = 1 + (opp_avg / my_avg)
        ratio = round(ratio, 2)
        
        # Open Modal with calculated odds in title
        # passing the constructed bet_type string like "PVP_DMG:OpponentName"
        await interaction.response.send_modal(BetAmountModal(f"DUEL ({ratio}x)", f"vs {opponent}"))

class BetAmountModal(Modal):
    def __init__(self, bet_type, target):
        super().__init__(title=f"Bet on {bet_type}")
        self.bet_type = bet_type
        self.target = target
        self.amount = TextInput(label="Amount", placeholder="100", min_length=1, max_length=5)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except:
            await interaction.response.send_message("❌ Invalid amount.", ephemeral=True)
            return
        
        if db.place_bet(interaction.user.id, self.bet_type, self.target, amt):
            await interaction.response.send_message(f"✅ **Bet Placed:** {amt} coins on {self.bet_type} ({self.target})", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Broke! You have {db.get_balance(interaction.user.id)} coins.", ephemeral=True)

class PlayerSelectView(View):
    def __init__(self, bet_type, players):
        super().__init__()
        # Ensure we only take first 25 players to fit Discord limit
        options = [discord.SelectOption(label=p, description="Clan Member") for p in players[:25]]
        select = Select(placeholder="Select a Player...", options=options)
        select.callback = self.callback
        self.bet_type = bet_type
        self.add_item(select)
    
    async def callback(self, interaction: discord.Interaction):
        target = interaction.data['values'][0]
        await interaction.response.send_modal(BetAmountModal(self.bet_type, target))

class BettingView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def check(self, i):
        if db.get_game_state('betting_status') != "OPEN":
            await i.response.send_message("❌ Betting Closed.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🍗 Win (x10)", style=discord.ButtonStyle.green, emoji="🍗")
    async def b_win(self, i: discord.Interaction, b: Button):
        if await self.check(i): await i.response.send_modal(BetAmountModal("WIN", "Squad"))

    @discord.ui.button(label="🔟 Top 10 (x2)", style=discord.ButtonStyle.primary, emoji="🔟")
    async def b_top10(self, i: discord.Interaction, b: Button):
        if await self.check(i): await i.response.send_modal(BetAmountModal("TOP10", "Squad"))

    @discord.ui.button(label="💀 First Die (x3)", style=discord.ButtonStyle.danger, emoji="💀")
    async def b_die(self, i: discord.Interaction, b: Button):
        if await self.check(i):
            # Fetch players from DB to populate dropdown
            # We need to access DB via the module
            import sqlite3
            conn = sqlite3.connect('clan.db')
            players = [r[0] for r in conn.execute("SELECT pubg_name FROM players").fetchall()]
            conn.close()
            if not players: await i.response.send_message("❌ No players registered.", ephemeral=True)
            else: await i.response.send_message("Who will die first?", view=PlayerSelectView("FIRST_DIE", players), ephemeral=True)

    @discord.ui.button(label="💥 Most Dmg (x3)", style=discord.ButtonStyle.secondary, emoji="💥")
    async def b_dmg(self, i: discord.Interaction, b: Button):
        if await self.check(i):
            import sqlite3
            conn = sqlite3.connect('clan.db')
            players = [r[0] for r in conn.execute("SELECT pubg_name FROM players").fetchall()]
            conn.close()
            if not players: await i.response.send_message("❌ No players registered.", ephemeral=True)
            else: await i.response.send_message("Who will deal most damage?", view=PlayerSelectView("MOST_DMG", players), ephemeral=True)
    @discord.ui.button(label="⚔️ 1v1 Duel", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def b_pvp(self, i: discord.Interaction, b: Button):
        if await self.check(i):
            import database as db
            # We need the bettor's PUBG name to exclude them from list & calc stats
            player = db.get_player_by_discord_id(i.user.id)
            if not player:
                await i.response.send_message("❌ You must `!register` to duel.", ephemeral=True)
                return
            
            await i.response.send_message(
                "⚔️ **Select your opponent!**\n*You are betting that YOU will out-damage them.*", 
                view=PvPOpponentSelectView(player[0], i.user.id), 
                ephemeral=True
            )