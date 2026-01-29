import discord
from discord.ui import Button, View, Modal, TextInput, Select
import database as db

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