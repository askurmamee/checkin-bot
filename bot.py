# ====================== SETTINGS ======================
import os
import sys
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import random

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") # ← set this in Railway's Variables tab
TZ = ZoneInfo("Asia/Shanghai") # UTC+8
# Persistent DB path. Set DB_PATH=/data/checkins.db in Railway once you've
# attached a volume mounted at /data. Falls back to a local file so this
# still runs fine on your own machine without a volume.
DB_PATH = os.getenv("DB_PATH", "checkins.db")
if not TOKEN:
    sys.exit(
        "ERROR: DISCORD_TOKEN is not set. "
        "Add it in Railway → your service → Variables (or a local .env file)."
    )
# ======================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def get_db():
    # Use a connection timeout and WAL mode to reduce "database is locked"
    # errors when sqlite is accessed concurrently. check_same_thread=False
    # allows connections to be used across threads safely when each
    # command opens its own connection.
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        # If PRAGMA fails for any reason, ignore — the DB will still work.
        pass
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
    c.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('start_date', ?)",
        (date_str,),
    )
    conn.commit()
    conn.close()

# Helper to save/get checkin message for a given day
def set_checkin_message(day, channel_id, message_id):
    conn = get_db()
    c = conn.cursor()
    key = f"checkin_message_{day}"
    value = f"{channel_id}:{message_id}"
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_checkin_message(day):
    conn = get_db()
    c = conn.cursor()
    key = f"checkin_message_{day}"
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row and row["value"]:
        try:
            ch, mid = row["value"].split(":")
            return int(ch), int(mid)
        except Exception:
            return None
    return None

def clear_checkin_messages():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM settings WHERE key LIKE 'checkin_message_%'")
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
    print(f"Using database at: {os.path.abspath(DB_PATH)}")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

@tree.command(name="checkin", description="Check in for today")
async def checkin(interaction: discord.Interaction):
    day = get_current_event_day()
    if day is None:
        await interaction.response.send_message(
            "The event is not active right now or start date is not set.",
            ephemeral=True,
        )
        return
    user_id = interaction.user.id
    conn = get_db()
    c = conn.cursor()
    # Check if already checked in today
    c.execute(
        "SELECT 1 FROM checkins WHERE user_id = ? AND event_day = ?",
        (user_id, day),
    )
    if c.fetchone():
        conn.close()
        await interaction.response.send_message(
            f"You already checked in for Day {day} today!", ephemeral=True
        )
        return
    # Save check-in
    c.execute(
        "INSERT INTO checkins (user_id, event_day) VALUES (?, ?)", (user_id, day)
    )
    conn.commit()
    # Count progress
    c.execute("SELECT COUNT(*) as cnt FROM checkins WHERE user_id = ?", (user_id,))
    progress = c.fetchone()["cnt"]
    conn.close()
    await interaction.response.send_message(
        f" **Checked in for Day {day}!**\nYour progress: **{progress}/7**",
        ephemeral=False,
    )

@tree.command(name="progress", description="See your check-in progress")
async def progress(interaction: discord.Interaction):
    user_id = interaction.user.id
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT event_day FROM checkins WHERE user_id = ? ORDER BY event_day",
        (user_id,),
    )
    days = [row["event_day"] for row in c.fetchall()]
    conn.close()
    progress = len(days)
    days_str = ", ".join(str(d) for d in days) if days else "None"
    await interaction.response.send_message(
        f"**Your progress: {progress}/7**\nDays completed: {days_str}",
        ephemeral=True,
    )

@app_commands.checks.has_permissions(administrator=True)
@tree.command(name="setstartdate", description="ADMIN: Set the event start date (YYYY-MM-DD)")
@app_commands.describe(date="Start date in YYYY-MM-DD format (example: 2026-09-05)")
async def setstartdate(interaction: discord.Interaction, date: str):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message(
            "Wrong format. Use YYYY-MM-DD (example: 2026-09-05)", ephemeral=True
        )
        return
    set_start_date(date)
    await interaction.response.send_message(
        f" Event start date set to **{date}** (Day 1)", ephemeral=True
    )

@app_commands.checks.has_permissions(administrator=True)
@tree.command(name="dailydraw", description="ADMIN: Draw 1 Daily Lucky Star winner")
async def dailydraw(interaction: discord.Interaction):
    day = get_current_event_day()
    if day is None:
        await interaction.response.send_message(
            "Event is not active today.", ephemeral=True
        )
        return
    # Defer immediately: fetch_user() below makes a Discord API call that can
    # take longer than the 3-second interaction window, especially with
    # several candidates.
    await interaction.response.defer()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM checkins WHERE event_day = ?", (day,))
    users = [row["user_id"] for row in c.fetchall()]
    conn.close()
    if not users:
        await interaction.followup.send("No one checked in today.", ephemeral=True)
        return
    winner_id = random.choice(users)
    winner = await bot.fetch_user(winner_id)
    await interaction.followup.send(
        f" **Daily Lucky Star Winner (Day {day})** \n"
        f"Congratulations {winner.mention}!\n"
        f"You won **1 SC**!"
    )

@app_commands.checks.has_permissions(administrator=True)
@tree.command(name="finaldraw", description="ADMIN: Draw the Final Lucky Draw winners (only players with 7/7)")
async def finaldraw(interaction: discord.Interaction):
    # Defer immediately: this command can fetch up to 14 users sequentially,
    # which will blow past Discord's 3-second interaction deadline.
    await interaction.response.defer()
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
        await interaction.followup.send(
            f"Not enough players with 7/7 yet. Currently: {len(users)} players.",
            ephemeral=True,
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
    message = " **FINAL LUCKY DRAW WINNERS** \n\n" + "\n".join(results)
    await interaction.followup.send(message)

@app_commands.checks.has_permissions(administrator=True)
@tree.command(name="eligible", description="ADMIN: Show how many players have 7/7")
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
    await interaction.response.send_message(
        f"Players with 7/7: **{count}**", ephemeral=True
    )

# New admin command: reset the giveaway (clear check-ins and set start date to today)
@app_commands.checks.has_permissions(administrator=True)
@tree.command(name="resetgiveaway", description="ADMIN: Reset giveaway — clear all check-ins and start today")
async def resetgiveaway(interaction: discord.Interaction):
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins")
    c.execute("DELETE FROM settings WHERE key LIKE 'checkin_message_%'")
    conn.commit()
    conn.close()
    set_start_date(today_str)
    await interaction.response.send_message(f"Giveaway reset. Start date set to {today_str}. All check-ins cleared.", ephemeral=True)

# New admin command: post check-in message for the current day (bot will add 👍)
@app_commands.checks.has_permissions(administrator=True)
@tree.command(name="postcheckin", description="ADMIN: Post a check-in message for today and add 👍 reaction")
async def postcheckin(interaction: discord.Interaction):
    day = get_current_event_day()
    if day is None:
        await interaction.response.send_message("Event is not active today. Set a start date first.", ephemeral=True)
        return
    # Send a message to the current channel and add a 👍 reaction
    channel = interaction.channel
    msg = await channel.send(f"React with 👍 to check in for Day {day}!")
    try:
        await msg.add_reaction('👍')
    except Exception:
        pass
    set_checkin_message(day, channel.id, msg.id)
    await interaction.response.send_message("Check-in message posted and 👍 added.", ephemeral=True)

# Reaction handlers: use raw events so they work even if the message isn't cached
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Ignore the bot's own reactions
    if payload.user_id == bot.user.id:
        return
    # Only care about 👍 reactions
    try:
        emoji = str(payload.emoji)
    except Exception:
        return
    if emoji != '👍':
        return
    day = get_current_event_day()
    if day is None:
        return
    stored = get_checkin_message(day)
    if not stored:
        return
    channel_id, message_id = stored
    if payload.message_id != message_id:
        return
    user_id = payload.user_id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT 1 FROM checkins WHERE user_id = ? AND event_day = ?", (user_id, day))
    if not c.fetchone():
        c.execute("INSERT INTO checkins (user_id, event_day) VALUES (?, ?)", (user_id, day))
        conn.commit()
        # Try to DM the user as confirmation (may fail if DMs are closed)
        try:
            user = await bot.fetch_user(user_id)
            await user.send(f"Checked in for Day {day}! 🎉")
        except Exception:
            pass
    conn.close()

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    try:
        emoji = str(payload.emoji)
    except Exception:
        return
    if emoji != '👍':
        return
    day = get_current_event_day()
    if day is None:
        return
    stored = get_checkin_message(day)
    if not stored:
        return
    channel_id, message_id = stored
    if payload.message_id != message_id:
        return
    user_id = payload.user_id
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins WHERE user_id = ? AND event_day = ?", (user_id, day))
    conn.commit()
    conn.close()
    # Try to DM the user as confirmation of removal
    try:
        user = await bot.fetch_user(user_id)
        await user.send(f"Your check-in for Day {day} has been removed.")
    except Exception:
        pass

# Error handler for missing permissions
@setstartdate.error
@dailydraw.error
@finaldraw.error
@eligible.error
@resetgiveaway.error
@postcheckin.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need Administrator permission to use this command.",
            ephemeral=True,
        )
    else:
        raise error

bot.run(TOKEN)
