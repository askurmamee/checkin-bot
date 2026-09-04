# ====================== SETTINGS ======================
import os
import sys
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime, time
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
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Global variable to store the checkin channel and message
CHECKIN_CHANNEL_ID = None
CHECKIN_MESSAGE_ID = None

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
    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_messages (
    date TEXT PRIMARY KEY,
    channel_id TEXT,
    message_id TEXT
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
    
    # Start the midnight auto-post task
    if not midnight_post_task.is_running():
        midnight_post_task.start()

# ====================== TASKS ======================
@tasks.loop(minutes=1)
async def midnight_post_task():
    """Check every minute if it's midnight and post a new checkin message."""
    now = datetime.now(TZ)
    
    # Check if it's exactly midnight (00:00)
    if now.hour == 0 and now.minute == 0:
        # Get the default checkin channel
        # For now, we'll need the channel ID to be set
        # In production, you'd want to store this in settings
        print("Midnight reached! Posting daily checkin message...")
        
        # Get all channels to find the first available guild
        for guild in bot.guilds:
            # Find a channel or use the first available
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await post_daily_checkin(channel)
                    break
        
        # Wait until next minute to avoid duplicate posts
        import asyncio
        await asyncio.sleep(60)

async def post_daily_checkin(channel):
    """Post the daily checkin message with thumbs up reaction."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    message_text = f"**Daily Check-in — {today}**\n\nReact with 👍 to check in for today!"
    
    try:
        message = await channel.send(message_text)
        await message.add_reaction("👍")
        
        # Save to database
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO daily_messages (date, channel_id, message_id) VALUES (?, ?, ?)",
            (today, str(channel.id), str(message.id))
        )
        conn.commit()
        conn.close()
        
        print(f"Posted daily checkin message: {message.id}")
    except Exception as e:
        print(f"Error posting daily checkin: {e}")

@bot.event
async def on_reaction_add(reaction, user):
    """Handle thumbs up reaction for check-ins."""
    # Ignore bot reactions
    if user.bot:
        return
    
    # Only listen for thumbs up reactions
    if str(reaction.emoji) != "👍":
        return
    
    # Check if this is a daily checkin message
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT date FROM daily_messages WHERE message_id = ?", (str(reaction.message.id),))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return
    
    # Record the check-in
    day = get_current_event_day()
    if day is None:
        return
    
    user_id = user.id
    conn = get_db()
    c = conn.cursor()
    
    # Check if already checked in today
    c.execute(
        "SELECT 1 FROM checkins WHERE user_id = ? AND event_day = ?",
        (user_id, day),
    )
    if c.fetchone():
        conn.close()
        return  # Already checked in
    
    # Save check-in
    c.execute(
        "INSERT INTO checkins (user_id, event_day) VALUES (?, ?)",
        (user_id, day)
    )
    conn.commit()
    conn.close()
    
    print(f"User {user.name} checked in via reaction")

# ====================== USER COMMANDS ======================
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

# ====================== ADMIN COMMANDS ======================
@tree.command(name="setstartdate", description="ADMIN: Set the event start date (YYYY-MM-DD)")
@app_commands.describe(date="Start date in YYYY-MM-DD format (example: 2026-09-05")
@app_commands.checks.has_permissions(administrator=True)
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

@tree.command(name="dailydraw", description="ADMIN: Draw 1 Daily Lucky Star winner")
@app_commands.checks.has_permissions(administrator=True)
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

@tree.command(name="finaldraw", description="ADMIN: Draw the Final Lucky Draw winners (only players with 7/7)")
@app_commands.checks.has_permissions(administrator=True)
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
    await interaction.response.send_message(
        f"Players with 7/7: **{count}**", ephemeral=True
    )

@tree.command(name="totalcount", description="ADMIN: Show total check-ins across all members")
@app_commands.checks.has_permissions(administrator=True)
async def totalcount(interaction: discord.Interaction):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM checkins")
    total = c.fetchone()["cnt"]
    conn.close()
    await interaction.response.send_message(
        f"**Total check-ins: {total}**", ephemeral=True
    )

@tree.command(name="resetmembers", description="ADMIN: Reset all members' check-in counts to 0")
@app_commands.checks.has_permissions(administrator=True)
async def resetmembers(interaction: discord.Interaction):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins")
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        "✅ All members' check-in counts have been reset to 0!", ephemeral=True
    )

@tree.command(name="masterreset", description="ADMIN: Complete event reset (clear all data)")
@app_commands.checks.has_permissions(administrator=True)
async def masterreset(interaction: discord.Interaction):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins")
    c.execute("DELETE FROM settings")
    c.execute("DELETE FROM daily_messages")
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        "🔄 **MASTER RESET COMPLETE** - All data cleared, event ready to restart!", ephemeral=True
    )

@tree.command(name="editmember", description="ADMIN: Edit a member's total check-in count")
@app_commands.describe(
    user="The user to edit",
    value="Value to add or subtract (e.g., +2 or -1)"
)
@app_commands.checks.has_permissions(administrator=True)
async def editmember(interaction: discord.Interaction, user: discord.User, value: str):
    try:
        change = int(value)
    except ValueError:
        await interaction.response.send_message(
            "Invalid value! Use a number like +2 or -1", ephemeral=True
        )
        return
    
    conn = get_db()
    c = conn.cursor()
    
    # Get current count
    c.execute("SELECT COUNT(*) as cnt FROM checkins WHERE user_id = ?", (user.id,))
    current = c.fetchone()["cnt"]
    new_count = max(0, current + change)  # Don't go below 0
    
    # Clear existing records
    c.execute("DELETE FROM checkins WHERE user_id = ?", (user.id,))
    
    # Re-add with new count (assign to days 1-7 or however many)
    for day in range(1, new_count + 1):
        if day <= 7:  # Cap at 7
            c.execute(
                "INSERT INTO checkins (user_id, event_day) VALUES (?, ?)",
                (user.id, day)
            )
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(
        f"✅ Updated {user.mention}'s check-ins: **{current}** → **{new_count}**", ephemeral=True
    )

@tree.command(name="postdailycheckin", description="ADMIN: Manually post today's check-in message")
@app_commands.checks.has_permissions(administrator=True)
async def postdailycheckin(interaction: discord.Interaction):
    await post_daily_checkin(interaction.channel)
    await interaction.response.send_message("✅ Daily check-in message posted!", ephemeral=True)

# Error handler for missing permissions
@setstartdate.error
@dailydraw.error
@finaldraw.error
@eligible.error
@totalcount.error
@resetmembers.error
@masterreset.error
@editmember.error
@postdailycheckin.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need Administrator permission to use this command.",
            ephemeral=True,
        )
    else:
        raise error

bot.run(TOKEN)
