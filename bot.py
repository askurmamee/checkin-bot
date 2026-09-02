# Async Discord check-in bot using aiosqlite
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
import logging
import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is not set. Add it to your environment or .env file.")

TZ = ZoneInfo("Asia/Shanghai")  # UTC+8

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Database setup
DB_FILE = "checkin.db"

async def init_db():
    """Create the database and tables if they don't exist."""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS checkins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    checkin_count INTEGER DEFAULT 0,
                    last_checkin TEXT
                )
            """)
            await db.commit()
        logger.info("Database initialized (%s)", DB_FILE)
    except Exception as e:
        logger.exception("Failed to initialize database: %s", e)

@bot.event
async def on_ready():
    logger.info("✅ %s is online!", bot.user)
    await init_db()
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d command(s)", len(synced))
    except Exception:
        logger.exception("Failed to sync commands")

@bot.tree.command(name="checkin", description="Check in for the day!")
async def checkin(interaction: discord.Interaction):
    user_id = interaction.user.id
    username = interaction.user.name
    now = datetime.now(tz=TZ).isoformat()

    try:
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute("SELECT checkin_count FROM checkins WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    "UPDATE checkins SET checkin_count = checkin_count + 1, last_checkin = ? WHERE user_id = ?",
                    (now, user_id),
                )
            else:
                await db.execute(
                    "INSERT INTO checkins (user_id, username, checkin_count, last_checkin) VALUES (?, ?, 1, ?)",
                    (user_id, username, now),
                )
            await db.commit()

            cursor = await db.execute("SELECT checkin_count FROM checkins WHERE user_id = ?", (user_id,))
            count_row = await cursor.fetchone()
            count = count_row[0] if count_row else 0

        await interaction.response.send_message(f"✅ Check-in successful! Total: {count} times")
    except Exception as e:
        logger.exception("Error in /checkin: %s", e)
        await interaction.response.send_message("❌ Something went wrong while recording your check-in.")

@bot.tree.command(name="stats", description="View your check-in stats")
async def stats(interaction: discord.Interaction):
    user_id = interaction.user.id
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute("SELECT checkin_count, last_checkin FROM checkins WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()

        if row:
            count, last = row
            await interaction.response.send_message(f"📊 Your stats:\nCheck-ins: {count}\nLast: {last}")
        else:
            await interaction.response.send_message("No check-ins yet! Use /checkin to start.")
    except Exception as e:
        logger.exception("Error in /stats: %s", e)
        await interaction.response.send_message("❌ Something went wrong while fetching your stats.")

if __name__ == '__main__':
    try:
        bot.run(TOKEN)
    except Exception:
        logger.exception("Bot terminated unexpectedly")
