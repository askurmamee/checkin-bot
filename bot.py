# ====================== SETTINGS ======================
import os

TOKEN = os.getenv("TOKEN")
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import random

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
"          # ← Put your bot token here
TZ = ZoneInfo("Asia/Shanghai")         # UTC+8
# ======================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def get_db():
    conn = sqlite3.connect("checkins.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            user_id INTEGER,
            event_day INTEGER,
            PRIMARY KEY (user_id, event_day)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_start_date():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'start_date'")
    row = c.fetchone()
    conn.close()
    if row:
        return datetime.strptime(row["value"], "%Y-%m-%d").date()
    return None

def set_start_date(date_str):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('start_date', ?)", (date_str,))
    conn.commit()
    conn.close()

def get_current_event_day():
    start = get_start_date()
    if not start:
        return None
    today = datetime.now(TZ).date()
    day_num = (today - start).days + 1
    if 1 <= day_num <= 7:
        return day_num
    return None

@bot.event
async def on_ready():
    init_db()
    print(f"Bot is online as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

@tree.command(name="checkin", description="Check in for today")
async def checkin(interaction: discord.Interaction):
    day = get_current_event_day()
    if day is None:
        await interaction.response.send_message("The event is not active right now or start date is not set.", ephemeral=True)
        return

    user_id = interaction.user.id
    conn = get_db()
    c = conn.cursor()

    # Check if already checked in today
    c.execute("SELECT 1 FROM checkins WHERE user_id = ? AND event_day = ?", (user_id, day))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message(f"You already checked in for Day {day} today!", ephemeral=True)
        return

    # Save check-in
    c.execute("INSERT INTO checkins (user_id, event_day) VALUES (?, ?)", (user_id, day))
    conn.commit()

    # Count progress
    c.execute("SELECT COUNT(*) as cnt FROM checkins WHERE user_id = ?", (user_id,))
    progress = c.fetchone()["cnt"]
    conn.close()

    await interaction.response.send_message(
        f"✅ **Checked in for Day {day}!**\nYour progress: **{progress}/7**",
        ephemeral=False
    )

@tree.command(name="progress", description="See your check-in progress")
async def progress(interaction: discord.Interaction):
    user_id = interaction.user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT event_day FROM checkins WHERE user_id = ? ORDER BY event_day", (user_id,))
    days = [row["event_day"] for row in c.fetchall()]
    conn.close()

    progress = len(days)
    days_str = ", ".join(str(d) for d in days) if days else "None"

    await interaction.response.send_message(
        f"**Your progress: {progress}/7**\nDays completed: {days_str}",
        ephemeral=True
    )

@tree.command(name="setstartdate", description="ADMIN: Set the event start date (YYYY-MM-DD)")
@app_commands.describe(date="Start date in YYYY-MM-DD format (example: 2026-09-05)")
@app_commands.checks.has_permissions(administrator=True)
async def setstartdate(interaction: discord.Interaction, date: str):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message("Wrong format. Use YYYY-MM-DD (example: 2026-09-05)", ephemeral=True)
        return

    set_start_date(date)
    await interaction.response.send_message(f"✅ Event start date set to **{date}** (Day 1)", ephemeral=True)

@tree.command(name="dailydraw", description="ADMIN: Draw 1 Daily Lucky Star winner for today")
@app_commands.checks.has_permissions(administrator=True)
async def dailydraw(interaction: discord.Interaction):
    day = get_current_event_day()
    if day is None:
        await interaction.response.send_message("Event is not active today.", ephemeral=True)
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM checkins WHERE event_day = ?", (day,))
    users = [row["user_id"] for row in c.fetchall()]
    conn.close()

    if not users:
        await interaction.response.send_message("No one checked in today.", ephemeral=True)
        return

    winner_id = random.choice(users)
    winner = await bot.fetch_user(winner_id)

    await interaction.response.send_message(
        f"🌟 **Daily Lucky Star Winner (Day {day})** 🌟\n"
        f"Congratulations {winner.mention}!\n"
        f"You won **1 SC**!"
    )

@tree.command(name="finaldraw", description="ADMIN: Draw the Final Lucky Draw winners (only 7/7 players)")
@app_commands.checks.has_permissions(administrator=True)
async def finaldraw(interaction: discord.Interaction):
    conn = get_db()
    c = conn.cursor()

    # Get users who have all 7 days
    c.execute("""
        SELECT user_id FROM checkins
        GROUP BY user_id
        HAVING COUNT(DISTINCT event_day) = 7
    """)
    users = [row["user_id"] for row in c.fetchall()]
    conn.close()

    if len(users) < 14:
        await interaction.response.send_message(
            f"Not enough players with 7/7 yet. Currently: {len(users)} players.",
            ephemeral=True
        )
        return

    random.shuffle(users)

    # Prizes
    prizes = (
        [("10 SC", 1)] +
        [("5 SC", 3)] +
        [("1 SC", 10)]
    )

    results = []
    index = 0
    for prize_name, count in prizes:
        for _ in range(count):
            if index >= len(users):
                break
            uid = users[index]
            member = await bot.fetch_user(uid)
            results.append(f"**{prize_name}** → {member.mention}")
            index += 1

    message = "🏆 **FINAL LUCKY DRAW WINNERS** 🏆\n\n" + "\n".join(results)
    await interaction.response.send_message(message)

@tree.command(name="eligible", description="ADMIN: Show how many players have 7/7")
@app_commands.checks.has_permissions(administrator=True)
async def eligible(interaction: discord.Interaction):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) as cnt FROM (
            SELECT user_id FROM checkins
            GROUP BY user_id
            HAVING COUNT(DISTINCT event_day) = 7
        )
    """)
    count = c.fetchone()["cnt"]
    conn.close()
    await interaction.response.send_message(f"Players with 7/7: **{count}**", ephemeral=True)

# Error handler for missing permissions
@setstartdate.error
@dailydraw.error
@finaldraw.error
@eligible.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need Administrator permission to use this command.", ephemeral=True)
    else:
        raise error

bot.run(TOKEN)
