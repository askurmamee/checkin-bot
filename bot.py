# ====================== SETTINGS ======================
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import random

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")          # ← Put your bot token here
TZ = ZoneInfo("Asia/Shanghai")               # UTC+8
# ======================================================

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Database setup
DB_FILE = "checkin.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            checkin_count INTEGER DEFAULT 0,
            last_checkin TEXT
        )
    """)
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online!")
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="checkin", description="Check in for the day!")
async def checkin(interaction: discord.Interaction):
    user_id = interaction.user.id
    username = interaction.user.name
    now = datetime.now(tz=TZ).isoformat()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT checkin_count FROM checkins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result:
        cursor.execute("UPDATE checkins SET checkin_count = checkin_count + 1, last_checkin = ? WHERE user_id = ?", 
                      (now, user_id))
    else:
        cursor.execute("INSERT INTO checkins (user_id, username, checkin_count, last_checkin) VALUES (?, ?, 1, ?)",
                      (user_id, username, now))
    
    conn.commit()
    cursor.execute("SELECT checkin_count FROM checkins WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    
    await interaction.response.send_message(f"✅ Check-in successful! Total: {count} times")

@bot.tree.command(name="stats", description="View your check-in stats")
async def stats(interaction: discord.Interaction):
    user_id = interaction.user.id
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT checkin_count, last_checkin FROM checkins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        count, last = result
        await interaction.response.send_message(f"📊 Your stats:\nCheck-ins: {count}\nLast: {last}")
    else:
        await interaction.response.send_message("No check-ins yet! Use /checkin to start.")

# Run the bot
bot.run(TOKEN)
