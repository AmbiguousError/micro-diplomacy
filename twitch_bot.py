"""
Micro-Diplomacy Twitch Chat Bot
Handles !bet commands, virtual currency (Diplobucks), and match payouts.
"""

import asyncio
from twitchio.ext import commands
import aiosqlite
from fastapi import FastAPI, Request
import uvicorn

# --- TWITCH BOT SETUP ---
class DiplobucksBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token="oauth:YOUR_TWITCH_BOT_TOKEN",
            prefix="!",
            initial_channels=["your_twitch_channel"]
        )
        self.db = None
        self.current_match_bets = {"Red": [], "Blue": [], "Green": [], "Yellow": []}
        self.betting_open = True

    async def event_ready(self):
        self.db = await aiosqlite.connect("diplobucks.db")
        await self.db.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, balance INTEGER)")
        await self.db.commit()
        print(f"🎮 Twitch Bot connected as {self.nick}")

    async def get_balance(self, username: str) -> int:
        async with self.db.execute("SELECT balance FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
            if row: return row[0]
            # Give new viewers a 1,000 Diplobucks stimulus check
            await self.db.execute("INSERT INTO users (username, balance) VALUES (?, 1000)", (username,))
            await self.db.commit()
            return 1000

    @commands.command(name="bal")
    async def cmd_balance(self, ctx: commands.Context):
        bal = await self.get_balance(ctx.author.name)
        await ctx.send(f"💰 @{ctx.author.name}, you have {bal} Diplobucks.")

    @commands.command(name="bet")
    async def cmd_bet(self, ctx: commands.Context):
        if not self.betting_open:
            return await ctx.send(f"⚠️ Betting is closed for the current match, @{ctx.author.name}!")

        parts = ctx.message.content.split()
        if len(parts) != 3:
            return await ctx.send("Usage: !bet <Faction> <Amount> (e.g., !bet Red 500)")

        faction = parts[1].capitalize()
        if faction not in self.current_match_bets:
            return await ctx.send("❌ Valid factions: Red, Blue, Green, Yellow.")

        try:
            amount = int(parts[2])
        except ValueError:
            return await ctx.send("❌ Amount must be a number.")

        bal = await self.get_balance(ctx.author.name)
        if amount > bal or amount <= 0:
            return await ctx.send(f"❌ Invalid amount. You have {bal} Diplobucks.")

        # Deduct balance and record bet
        await self.db.execute("UPDATE users SET balance = balance - ? WHERE username = ?", (amount, ctx.author.name))
        await self.db.commit()
        
        self.current_match_bets[faction].append((ctx.author.name, amount))
        await ctx.send(f"✅ @{ctx.author.name} bet {amount} on {faction}!")

    async def payout_winners(self, winning_faction: str):
        self.betting_open = False
        winners = self.current_match_bets.get(winning_faction, [])
        total_payout = 0
        
        # Simple 2x payout multiplier
        for username, amount in winners:
            winnings = amount * 2
            total_payout += winnings
            await self.db.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (winnings, username))
            
        await self.db.commit()
        
        channel = self.connected_channels[0]
        await channel.send(f"🏆 MATCH OVER! {winning_faction} wins! Paid out {total_payout} Diplobucks to the believers.")
        
        # Reset for next match
        self.current_match_bets = {"Red": [], "Blue": [], "Green": [], "Yellow": []}
        self.betting_open = True

bot = DiplobucksBot()

# --- WEBHOOK SERVER (Listens for FastAPI Game Engine) ---
webhook_app = FastAPI()

@webhook_app.post("/webhook/match_concluded")
async def match_concluded(request: Request):
    """Called by your main Micro-Diplomacy API when a match ends."""
    data = await request.json()
    winner = data.get("winner")  # e.g., "Blue"
    if winner:
        await bot.payout_winners(winner)
    return {"status": "payouts_processed"}

# --- RUNNER ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start())
    uvicorn.run(webhook_app, host="0.0.0.0", port=8001, loop="asyncio")
