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

import discord
import database as db

class BettingModal(discord.ui.Modal):
    def __init__(self, session_id, bet_type, title, placeholder="Amount"):
        super().__init__(title=title)
        self.session_id = session_id # Store the session ID
        self.bet_type = bet_type
        
        self.amount = discord.ui.TextInput(
            label="Bet Amount", 
            placeholder=placeholder,
            min_length=1, 
            max_length=6
        )
        self.add_item(self.amount)

        # For specific targets (like "Who will die first?"), add a second input
        self.target = None
        if bet_type in ["MOST_DMG", "FIRST_DIE", "DUEL"]:
            self.target = discord.ui.TextInput(
                label="Player Name",
                placeholder="Exact PUBG Name",
                min_length=3,
                max_length=20
            )
            self.add_item(self.target)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validate Amount
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except:
            return await interaction.response.send_message("❌ Please enter a valid positive number.", ephemeral=True)

        # 2. Check Balance
        user_id = interaction.user.id
        balance = db.get_balance(user_id)
        if balance < amt:
            return await interaction.response.send_message(f"❌ **Insufficient Funds!** You have {balance} coins.", ephemeral=True)

        # 3. Check Session Status (The Fix)
        # We check if THIS specific session is still OPEN
        status = db.get_session_status(self.session_id)
        if status != "OPEN":
            return await interaction.response.send_message(f"🔒 **Betting is CLOSED** for Round #{self.session_id}!", ephemeral=True)

        # 4. Place Bet
        target_val = self.target.value if self.target else "SQUAD"
        
        # Deduct Money
        db.update_balance(user_id, -amt)
        
        # Save to DB
        db.place_bet(self.session_id, user_id, self.bet_type, target_val, amt)
        
        await interaction.response.send_message(f"✅ **Bet Placed!** {amt} on {self.bet_type} (Round #{self.session_id})", ephemeral=True)


class BettingView(discord.ui.View):
    def __init__(self, session_id):
        super().__init__(timeout=None)
        self.session_id = session_id

    @discord.ui.button(label="🏆 Win (10x)", style=discord.ButtonStyle.primary, row=0)
    async def bet_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BettingModal(self.session_id, "WIN", "Bet on Win"))

    @discord.ui.button(label="🔟 Top 10 (2x)", style=discord.ButtonStyle.success, row=0)
    async def bet_top10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BettingModal(self.session_id, "TOP10", "Bet on Top 10"))

    @discord.ui.button(label="💀 First Die (3x)", style=discord.ButtonStyle.danger, row=1)
    async def bet_die(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BettingModal(self.session_id, "FIRST_DIE", "Who dies first?"))

    @discord.ui.button(label="💥 Most Dmg (3x)", style=discord.ButtonStyle.secondary, row=1)
    async def bet_dmg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BettingModal(self.session_id, "MOST_DMG", "Most Damage"))
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