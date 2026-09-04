import os
import random
import sqlite3
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TZ = ZoneInfo("Asia/Shanghai")
DB_PATH = os.getenv("DB_PATH", "checkins.db")
TARGET_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or "0") or None
CONFIGURED_CHANNEL_ID = int(os.getenv("CHECKIN_CHANNEL_ID", "0") or "0") or None
BUILD_SIGNATURE = "2026-09-04-refresh-11-commands"
EXPECTED_COMMAND_NAMES = (
    "checkin",
    "progress",
    "setstartdate",
    "dailydraw",
    "finaldraw",
    "eligible",
    "totalcount",
    "resetmembers",
    "masterreset",
    "editmember",
    "postdailycheckin",
)

if not TOKEN:
    sys.exit(
        "ERROR: DISCORD_TOKEN is not set. "
        "Add it in Railway → your service → Variables (or a local .env file)."
    )


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.DatabaseError:
        pass
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS checkins (
            user_id INTEGER,
            event_day INTEGER,
            PRIMARY KEY (user_id, event_day)
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_messages (
            date TEXT PRIMARY KEY,
            channel_id TEXT,
            message_id TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_setting(key: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(key: str, value: str):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_start_date():
    value = get_setting("start_date")
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def set_start_date(date_str: str):
    set_setting("start_date", date_str)


def get_checkin_channel_id():
    stored = get_setting("checkin_channel_id")
    if stored:
        return int(stored)
    return CONFIGURED_CHANNEL_ID


def set_checkin_channel_id(channel_id: int):
    set_setting("checkin_channel_id", str(channel_id))


def get_event_day_for_date(target_date: date):
    start = get_start_date()
    if not start:
        return None
    day_num = (target_date - start).days + 1
    if 1 <= day_num <= 7:
        return day_num
    return None


def get_current_event_day():
    return get_event_day_for_date(datetime.now(TZ).date())


def get_daily_message_for_date(date_str: str):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT date, channel_id, message_id FROM daily_messages WHERE date = ?",
        (date_str,),
    )
    row = c.fetchone()
    conn.close()
    return row


def get_daily_message_for_message(message_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT date, channel_id, message_id FROM daily_messages WHERE message_id = ?",
        (str(message_id),),
    )
    row = c.fetchone()
    conn.close()
    return row


def set_daily_message(date_str: str, channel_id: int, message_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO daily_messages (date, channel_id, message_id)
        VALUES (?, ?, ?)
        """,
        (date_str, str(channel_id), str(message_id)),
    )
    conn.commit()
    conn.close()


def record_checkin(user_id: int, event_day: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO checkins (user_id, event_day) VALUES (?, ?)",
        (user_id, event_day),
    )
    inserted = c.rowcount == 1
    conn.commit()
    conn.close()
    return inserted


def count_user_checkins(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM checkins WHERE user_id = ?", (user_id,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count


def get_user_checkin_days(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT event_day FROM checkins WHERE user_id = ? ORDER BY event_day",
        (user_id,),
    )
    days = [row["event_day"] for row in c.fetchall()]
    conn.close()
    return days


def get_day_checkins(event_day: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM checkins WHERE event_day = ?", (event_day,))
    users = [row["user_id"] for row in c.fetchall()]
    conn.close()
    return users


def get_fully_eligible_users():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id FROM checkins
        GROUP BY user_id
        HAVING COUNT(DISTINCT event_day) = 7
        """
    )
    users = [row["user_id"] for row in c.fetchall()]
    conn.close()
    return users


def count_eligible_users():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT COUNT(*) AS cnt FROM (
            SELECT user_id FROM checkins
            GROUP BY user_id
            HAVING COUNT(DISTINCT event_day) = 7
        )
        """
    )
    count = c.fetchone()["cnt"]
    conn.close()
    return count


def count_total_checkins():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM checkins")
    count = c.fetchone()["cnt"]
    conn.close()
    return count


def clear_all_checkins():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins")
    conn.commit()
    conn.close()


def master_reset_data():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins")
    c.execute("DELETE FROM settings")
    c.execute("DELETE FROM daily_messages")
    conn.commit()
    conn.close()


def set_member_checkin_total(user_id: int, total: int):
    target_total = max(0, min(total, 7))
    current_total = count_user_checkins(user_id)

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM checkins WHERE user_id = ?", (user_id,))
    for event_day in range(1, target_total + 1):
        c.execute(
            "INSERT INTO checkins (user_id, event_day) VALUES (?, ?)",
            (user_id, event_day),
        )
    conn.commit()
    conn.close()
    return current_total, target_total


intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class CheckInBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.startup_logged = False
        self.commands_synced = False
        self.local_command_names = []
        self.global_sync_count = 0
        self.guild_sync_counts = {}

    async def setup_hook(self):
        init_db()
        if CONFIGURED_CHANNEL_ID:
            set_checkin_channel_id(CONFIGURED_CHANNEL_ID)
        if not midnight_post_task.is_running():
            midnight_post_task.start()

    def validate_expected_commands(self):
        local_names = sorted(command.name for command in self.tree.get_commands())
        expected_names = sorted(EXPECTED_COMMAND_NAMES)
        if local_names != expected_names:
            raise RuntimeError(
                f"Expected {len(expected_names)} commands but loaded "
                f"{len(local_names)}: {local_names}"
            )
        self.local_command_names = local_names

    def validate_synced_commands(self, synced_commands, scope: str):
        synced_names = {command.name for command in synced_commands}
        missing_names = sorted(set(EXPECTED_COMMAND_NAMES) - synced_names)
        if missing_names:
            raise RuntimeError(
                f"Missing expected commands in {scope}: {missing_names}"
            )

    async def sync_registered_commands(self):
        self.validate_expected_commands()
        global_commands = await self.tree.sync()
        self.global_sync_count = len(global_commands)
        self.validate_synced_commands(global_commands, "global scope")

        guild_ids = []
        if TARGET_GUILD_ID:
            guild_ids = [TARGET_GUILD_ID]
        elif len(self.guilds) == 1:
            guild_ids = [guild.id for guild in self.guilds]

        self.guild_sync_counts = {}
        for guild_id in guild_ids:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self.guild_sync_counts[guild_id] = len(synced)
            self.validate_synced_commands(synced, f"guild {guild_id}")

        self.commands_synced = True


bot = CheckInBot()
tree = bot.tree


async def resolve_checkin_channel():
    channel_id = get_checkin_channel_id()
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if channel is not None and hasattr(channel, "send"):
            return channel
        print(f"Configured check-in channel {channel_id} is unavailable.")

    for guild in bot.guilds:
        me = guild.me
        if me is None:
            continue
        for channel in guild.text_channels:
            if channel.permissions_for(me).send_messages:
                set_checkin_channel_id(channel.id)
                return channel
    return None


async def post_daily_checkin(channel):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    existing = get_daily_message_for_date(today)
    if existing:
        return False, existing["message_id"]

    message_text = f"**Daily Check-in — {today}**\n\nReact with 👍 to check in for today!"
    message = await channel.send(message_text)
    await message.add_reaction("👍")
    set_daily_message(today, channel.id, message.id)
    set_checkin_channel_id(channel.id)
    print(f"Posted daily check-in message {message.id} in channel {channel.id}")
    return True, message.id


@bot.event
async def on_ready():
    if not bot.commands_synced:
        await bot.sync_registered_commands()

    if bot.startup_logged:
        return

    bot.startup_logged = True
    print(f"Bot build signature: {BUILD_SIGNATURE}")
    print(f"Bot is online as {bot.user}")
    print(f"Using database at: {os.path.abspath(DB_PATH)}")
    print(
        f"Loaded {len(bot.local_command_names)} commands locally: "
        f"{', '.join(bot.local_command_names)}"
    )
    print(f"Synced {bot.global_sync_count} commands globally")
    for guild_id, count in bot.guild_sync_counts.items():
        print(f"Synced {count} commands to guild {guild_id}")


@tasks.loop(minutes=1)
async def midnight_post_task():
    now = datetime.now(TZ)
    if now.hour != 0 or now.minute != 0:
        return

    channel = await resolve_checkin_channel()
    if channel is None:
        print("Midnight reached but no valid check-in channel is configured.")
        return

    created, message_id = await post_daily_checkin(channel)
    if created:
        print(f"Midnight auto-post created message {message_id}")
    else:
        print(f"Midnight auto-post skipped; today's message {message_id} already exists")


@midnight_post_task.before_loop
async def before_midnight_post_task():
    await bot.wait_until_ready()


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if bot.user is not None and payload.user_id == bot.user.id:
        return
    if str(payload.emoji) != "👍":
        return
    if payload.guild_id is None:
        return

    member = payload.member
    if member is None:
        guild = bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

    if member.bot:
        return

    record = get_daily_message_for_message(payload.message_id)
    if not record:
        return

    reaction_date = datetime.strptime(record["date"], "%Y-%m-%d").date()
    event_day = get_event_day_for_date(reaction_date)
    if event_day is None:
        return

    if not record_checkin(payload.user_id, event_day):
        return

    user_name = member.display_name
    print(f"Recorded 👍 reaction check-in for {user_name} on Day {event_day}")


@tree.command(name="checkin", description="Check in for today")
async def checkin(interaction: discord.Interaction):
    event_day = get_current_event_day()
    if event_day is None:
        await interaction.response.send_message(
            "The event is not active right now or the start date is not set.",
            ephemeral=True,
        )
        return

    if not record_checkin(interaction.user.id, event_day):
        await interaction.response.send_message(
            f"You already checked in for Day {event_day} today!",
            ephemeral=True,
        )
        return

    progress_count = count_user_checkins(interaction.user.id)
    await interaction.response.send_message(
        f"**Checked in for Day {event_day}!**\nYour progress: **{progress_count}/7**"
    )


@tree.command(name="progress", description="See your check-in progress")
async def progress(interaction: discord.Interaction):
    days = get_user_checkin_days(interaction.user.id)
    days_str = ", ".join(str(day) for day in days) if days else "None"
    await interaction.response.send_message(
        f"**Your progress: {len(days)}/7**\nDays completed: {days_str}",
        ephemeral=True,
    )


@tree.command(
    name="setstartdate", description="ADMIN: Set the event start date (YYYY-MM-DD)"
)
@app_commands.describe(date="Start date in YYYY-MM-DD format")
@app_commands.checks.has_permissions(administrator=True)
async def setstartdate(interaction: discord.Interaction, date: str):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message(
            "Wrong format. Use YYYY-MM-DD (example: 2026-09-05).",
            ephemeral=True,
        )
        return

    set_start_date(date)
    await interaction.response.send_message(
        f"Event start date set to **{date}** (Day 1).",
        ephemeral=True,
    )


@tree.command(name="dailydraw", description="ADMIN: Draw 1 Daily Lucky Star winner")
@app_commands.checks.has_permissions(administrator=True)
async def dailydraw(interaction: discord.Interaction):
    event_day = get_current_event_day()
    if event_day is None:
        await interaction.response.send_message(
            "Event is not active today.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()
    users = get_day_checkins(event_day)
    if not users:
        await interaction.followup.send("No one checked in today.", ephemeral=True)
        return

    winner_id = random.choice(users)
    winner = await bot.fetch_user(winner_id)
    await interaction.followup.send(
        f"**Daily Lucky Star Winner (Day {event_day})**\n"
        f"Congratulations {winner.mention}!\n"
        "You won **1 SC**!"
    )


@tree.command(
    name="finaldraw",
    description="ADMIN: Draw the Final Lucky Draw winners (only players with 7/7)",
)
@app_commands.checks.has_permissions(administrator=True)
async def finaldraw(interaction: discord.Interaction):
    await interaction.response.defer()
    users = get_fully_eligible_users()
    if len(users) < 14:
        await interaction.followup.send(
            f"Not enough players with 7/7 yet. Currently: {len(users)} players.",
            ephemeral=True,
        )
        return

    random.shuffle(users)
    prizes = [("10 SC", 1), ("5 SC", 3), ("1 SC", 10)]
    results = []
    index = 0
    for prize_name, count in prizes:
        for _ in range(count):
            if index >= len(users):
                break
            winner = await bot.fetch_user(users[index])
            results.append(f"**{prize_name}** → {winner.mention}")
            index += 1

    await interaction.followup.send(
        "**FINAL LUCKY DRAW WINNERS**\n\n" + "\n".join(results)
    )


@tree.command(name="eligible", description="ADMIN: Show how many players have 7/7")
@app_commands.checks.has_permissions(administrator=True)
async def eligible(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Players with 7/7: **{count_eligible_users()}**",
        ephemeral=True,
    )


@tree.command(
    name="totalcount", description="ADMIN: Show total check-ins across all members"
)
@app_commands.checks.has_permissions(administrator=True)
async def totalcount(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"**Total check-ins: {count_total_checkins()}**",
        ephemeral=True,
    )


@tree.command(
    name="resetmembers", description="ADMIN: Reset all members' check-in counts to 0"
)
@app_commands.checks.has_permissions(administrator=True)
async def resetmembers(interaction: discord.Interaction):
    clear_all_checkins()
    await interaction.response.send_message(
        "✅ All members' check-in counts have been reset to 0!",
        ephemeral=True,
    )


@tree.command(name="masterreset", description="ADMIN: Complete event reset (clear all data)")
@app_commands.checks.has_permissions(administrator=True)
async def masterreset(interaction: discord.Interaction):
    master_reset_data()
    await interaction.response.send_message(
        "🔄 **MASTER RESET COMPLETE** - All data cleared, event ready to restart!",
        ephemeral=True,
    )


@tree.command(name="editmember", description="ADMIN: Edit a member's total check-in count")
@app_commands.describe(
    user="The user to edit",
    value="Value to add or subtract (for example +2 or -1)",
)
@app_commands.checks.has_permissions(administrator=True)
async def editmember(interaction: discord.Interaction, user: discord.User, value: str):
    try:
        change = int(value)
    except ValueError:
        await interaction.response.send_message(
            "Invalid value! Use a number like +2 or -1.",
            ephemeral=True,
        )
        return

    current_total, new_total = set_member_checkin_total(
        user.id, count_user_checkins(user.id) + change
    )
    await interaction.response.send_message(
        f"✅ Updated {user.mention}'s check-ins: **{current_total}** → **{new_total}**",
        ephemeral=True,
    )


@tree.command(
    name="postdailycheckin", description="ADMIN: Manually post today's check-in message"
)
@app_commands.checks.has_permissions(administrator=True)
async def postdailycheckin(interaction: discord.Interaction):
    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        await interaction.response.send_message(
            "This command must be used in a text channel.",
            ephemeral=True,
        )
        return

    created, message_id = await post_daily_checkin(channel)
    if created:
        await interaction.response.send_message(
            "✅ Daily check-in message posted!",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"Today's daily check-in message already exists (message ID: {message_id}).",
            ephemeral=True,
        )


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
        if interaction.response.is_done():
            await interaction.followup.send(
                "You need Administrator permission to use this command.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "You need Administrator permission to use this command.",
                ephemeral=True,
            )
        return
    raise error


bot.run(TOKEN)
