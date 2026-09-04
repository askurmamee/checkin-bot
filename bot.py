# ====================== SETTINGS ======================
import os
import sys
import json
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
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
TZ = ZoneInfo("Asia/Shanghai") # UTC+8
# Persistent DB path. Set DB_PATH=/data/checkins.db in Railway once you've
# attached a volume mounted at /data. Falls back to a local file so this
# still runs fine on your own machine without a volume.
DB_PATH = os.getenv("DB_PATH", "checkins.db")
# ======================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
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
    with conn:
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
        user_id INTEGER,
        event_day INTEGER,
        event_start TEXT,
        PRIMARY KEY (user_id, event_day, event_start)
        )
        """)
        c.execute("PRAGMA table_info(checkins)")
        columns = {row["name"]: row["pk"] for row in c.fetchall()}
        needs_migration = (
            "event_start" not in columns or columns.get("event_start") != 3
        )
        if needs_migration:
            default_event_start = "legacy"
            c.execute("DROP TABLE IF EXISTS checkins_new")
            c.execute("""
            CREATE TABLE checkins_new (
            user_id INTEGER,
            event_day INTEGER,
            event_start TEXT,
            PRIMARY KEY (user_id, event_day, event_start)
            )
            """)
            if "event_start" in columns:
                c.execute(
                    """
                    INSERT OR IGNORE INTO checkins_new (user_id, event_day, event_start)
                    SELECT user_id, event_day, COALESCE(event_start, ?)
                    FROM checkins
                    """,
                    (default_event_start,),
                )
            else:
                c.execute(
                    """
                    INSERT OR IGNORE INTO checkins_new (user_id, event_day, event_start)
                    SELECT user_id, event_day, ?
                    FROM checkins
                    """,
                    (default_event_start,),
                )
            c.execute("DROP TABLE checkins")
            c.execute("ALTER TABLE checkins_new RENAME TO checkins")
        c.execute("""
        CREATE INDEX IF NOT EXISTS idx_checkins_event_day_user
        ON checkins (event_start, event_day, user_id)
        """)
    conn.close()

def read_start_date():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'start_date'")
    row = c.fetchone()
    conn.close()
    if not row:
        return None, "missing"
    if row:
        try:
            return datetime.strptime(row["value"], "%Y-%m-%d").date(), "valid"
        except ValueError:
            print(
                "Invalid start_date found in settings table. "
                "Reset it with /setstartdate YYYY-MM-DD."
            )
            return None, "invalid"

def get_start_date():
    start_date, _ = read_start_date()
    return start_date

def get_start_date_error_message():
    _, status = read_start_date()
    if status == "missing":
        return "No event is configured yet. Set a start date first."
    return "Stored event start date is invalid. Reset it with /setstartdate YYYY-MM-DD."

def get_sync_target():
    if not GUILD_ID:
        return None
    try:
        return discord.Object(id=int(GUILD_ID))
    except ValueError:
        print(f"Invalid DISCORD_GUILD_ID: {GUILD_ID!r}. Falling back to global sync.")
        return None

def get_event_start_key():
    start = get_start_date()
    return start.isoformat() if start else None

def get_setting(key):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else None

def set_setting(key, value):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.close()

def delete_setting(key):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.close()

def delete_settings_with_prefix(prefix):
    conn = get_db()
    with conn:
        conn.execute(
            "DELETE FROM settings WHERE key LIKE ?",
            (f"{prefix}%",),
        )
    conn.close()

def get_daily_close_key(event_start, day):
    return f"daily_closed:{event_start}:{day}"

def is_daily_checkin_closed(day, event_start=None):
    current_event_start = event_start or get_event_start_key()
    if not current_event_start:
        return False
    return get_setting(get_daily_close_key(current_event_start, day)) == "1"

def close_daily_checkin(day, event_start=None):
    current_event_start = event_start or get_event_start_key()
    if not current_event_start:
        return
    set_setting(get_daily_close_key(current_event_start, day), "1")

def clear_user_checkins(user_id, event_start):
    conn = get_db()
    with conn:
        cursor = conn.execute(
            "DELETE FROM checkins WHERE user_id = ? AND event_start = ?",
            (user_id, event_start),
        )
    conn.close()
    return cursor.rowcount

def clear_day_checkins(day, event_start):
    conn = get_db()
    with conn:
        cursor = conn.execute(
            "DELETE FROM checkins WHERE event_day = ? AND event_start = ?",
            (day, event_start),
        )
    conn.close()
    return cursor.rowcount

def clear_event_checkins(event_start):
    conn = get_db()
    with conn:
        cursor = conn.execute(
            "DELETE FROM checkins WHERE event_start = ?",
            (event_start,),
        )
    conn.close()
    return cursor.rowcount

def master_reset_data():
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM checkins")
        conn.execute("DELETE FROM settings")
    conn.close()

def store_last_winners(draw_type, winners, *, event_start=None, day=None):
    payload = {
        "event_start": event_start,
        "day": day,
        "winners": winners,
    }
    set_setting(f"last_winners:{draw_type}", json.dumps(payload))

def load_last_winners(draw_type):
    raw = get_setting(f"last_winners:{draw_type}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

def build_winner_dm(draw_type, winner_info, payload, custom_message=None):
    prize = winner_info.get("prize", "your prize")
    if draw_type == "daily":
        base_message = (
            f"🎉 You won the Daily Lucky Star draw for Day {payload.get('day')}! "
            f"Prize: **{prize}**."
        )
    else:
        base_message = (
            f"🎉 You won the final event draw for the event starting "
            f"**{payload.get('event_start')}**! Prize: **{prize}**."
        )
    if custom_message:
        return f"{base_message}\n\n{custom_message}"
    return base_message

def set_start_date(date_str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'start_date'")
    row = c.fetchone()
    changed = bool(not row or row["value"] != date_str)
    with conn:
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('start_date', ?)",
            (date_str,),
        )
    conn.close()
    return changed

def get_current_event_day():
    start = get_start_date()
    if not start:
        return None
    today = datetime.now(TZ).date()
    day_num = (today - start).days + 1
    if 1 <= day_num <= 7:
        return day_num
    return None

def get_total_checkins_for_day(day):
    event_start = get_event_start_key()
    if not event_start:
        return 0
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT COUNT(*) as cnt
        FROM checkins
        WHERE event_day = ? AND event_start = ?
        """,
        (day, event_start),
    )
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def chunk_lines(lines, prefix="", max_length=1900, repeat_prefix=False):
    def format_chunk(chunk_lines, include_prefix):
        body = "\n".join(chunk_lines)
        if include_prefix and prefix and body:
            return f"{prefix}\n{body}"
        if include_prefix and prefix:
            return prefix
        return body

    chunks = []
    current_lines = []
    include_prefix = bool(prefix)
    for line in lines:
        remaining = line
        while True:
            available = max_length - (
                len(prefix) + 1 if include_prefix and prefix else 0
            )
            if available <= 0:
                raise ValueError("Prefix is too long for the configured max_length.")

            segment = remaining[:available]
            rest = remaining[available:]
            candidate_lines = current_lines + [segment]
            candidate = format_chunk(candidate_lines, include_prefix)
            if len(candidate) > max_length and current_lines:
                chunks.append(format_chunk(current_lines, include_prefix))
                current_lines = []
                include_prefix = repeat_prefix and bool(prefix)
                continue

            current_lines = candidate_lines
            if not rest:
                break

            chunks.append(format_chunk(current_lines, include_prefix))
            current_lines = []
            include_prefix = repeat_prefix and bool(prefix)
            remaining = rest

    if current_lines or (prefix and not chunks):
        chunks.append(format_chunk(current_lines, include_prefix))
    return chunks

def admin_only():
    def decorator(func):
        wrapped = app_commands.checks.has_permissions(administrator=True)(func)
        setattr(wrapped, "__checkin_admin_command__", True)
        return wrapped
    return decorator

async def get_available_commands():
    try:
        sync_target = get_sync_target()
        if sync_target:
            registered = await tree.fetch_commands(guild=sync_target)
        else:
            registered = await tree.fetch_commands()
        return {command.name: command.description for command in registered}
    except discord.DiscordException:
        return {command.name: command.description for command in tree.get_commands()}

@bot.event
async def on_ready():
    init_db()
    print(f"Bot is online as {bot.user}")
    print(f"Using database at: {os.path.abspath(DB_PATH)}")
    try:
        sync_target = get_sync_target()
        if sync_target:
            synced = await tree.sync(guild=sync_target)
            print(f"Synced {len(synced)} commands to guild {sync_target.id}")
        else:
            synced = await tree.sync()
            print(f"Synced {len(synced)} global commands")
    except Exception as e:
        print(e)

@tree.command(name="checkin", description="Check in for today")
async def checkin(interaction: discord.Interaction):
    day = get_current_event_day()
    event_start = get_event_start_key()
    if day is None:
        await interaction.response.send_message(
            "The event is not active right now or start date is not set.",
            ephemeral=True,
        )
        return
    if is_daily_checkin_closed(day, event_start):
        await interaction.response.send_message(
            f"Day {day} check-in has been closed by an admin.",
            ephemeral=True,
        )
        return
    user_id = interaction.user.id
    conn = get_db()
    c = conn.cursor()
    # Check if already checked in today
    c.execute(
        """
        SELECT 1
        FROM checkins
        WHERE user_id = ? AND event_day = ? AND event_start = ?
        """,
        (user_id, day, event_start),
    )
    if c.fetchone():
        conn.close()
        await interaction.response.send_message(
            f"You already checked in for Day {day} today!", ephemeral=True
        )
        return
    # Save check-in
    c.execute(
        """
        INSERT INTO checkins (user_id, event_day, event_start)
        VALUES (?, ?, ?)
        """,
        (user_id, day, event_start),
    )
    conn.commit()
    # Count progress
    c.execute(
        """
        SELECT COUNT(*) as cnt
        FROM checkins
        WHERE user_id = ? AND event_start = ?
        """,
        (user_id, event_start),
    )
    progress = c.fetchone()["cnt"]
    conn.close()
    await interaction.response.send_message(
        f" **Checked in for Day {day}!**\nYour progress: **{progress}/7**",
        ephemeral=False,
    )

@tree.command(name="progress", description="See your check-in progress")
async def progress(interaction: discord.Interaction):
    user_id = interaction.user.id
    event_start = get_event_start_key()
    if not event_start:
        await interaction.response.send_message(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT event_day
        FROM checkins
        WHERE user_id = ? AND event_start = ?
        ORDER BY event_day
        """,
        (user_id, event_start),
    )
    days = [row["event_day"] for row in c.fetchall()]
    conn.close()
    progress = len(days)
    days_str = ", ".join(str(d) for d in days) if days else "None"
    await interaction.response.send_message(
        f"**Your progress: {progress}/7**\nDays completed: {days_str}",
        ephemeral=True,
    )

@tree.command(name="status", description="See the current event status")
async def status(interaction: discord.Interaction):
    start = get_start_date()
    day = get_current_event_day()
    if not start:
        await interaction.response.send_message(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return

    if day is None:
        await interaction.response.send_message(
            f"Event start date: **{start.isoformat()}**\nThe 7-day event is not active right now.",
            ephemeral=True,
        )
        return

    today_count = get_total_checkins_for_day(day)
    await interaction.response.send_message(
        f"Event start date: **{start.isoformat()}**\n"
        f"Current day: **Day {day}/7**\n"
        f"Today's check-ins: **{today_count}**\n"
        f"Today's check-in is **{'closed' if is_daily_checkin_closed(day) else 'open'}**.",
        ephemeral=True,
    )

@tree.command(name="leaderboard", description="Show the top check-in counts")
async def leaderboard(interaction: discord.Interaction):
    day = get_current_event_day()
    event_start = get_event_start_key()
    if day is None:
        await interaction.response.send_message(
            "Event is not active right now.",
            ephemeral=True,
        )
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT user_id, COUNT(*) as cnt
    FROM checkins
    WHERE event_start = ? AND event_day BETWEEN 1 AND ?
    GROUP BY user_id
    ORDER BY cnt DESC, user_id ASC
    LIMIT 10
    """, (event_start, day))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(
            "No check-ins have been recorded yet.",
            ephemeral=True,
        )
        return

    lines = []
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. User ID {row['user_id']} (<@{row['user_id']}>) — **{row['cnt']}/7**"
        )
    await interaction.response.send_message(
        "**Check-in Leaderboard**\n" + "\n".join(lines),
        ephemeral=False,
    )

@tree.command(name="commands", description="Show available bot commands")
async def commands(interaction: discord.Interaction):
    available_commands = await get_available_commands()
    local_commands = {
        command.name: command for command in tree.get_commands()
    }
    user_commands = []
    admin_commands = []
    for command_name, description in sorted(available_commands.items()):
        local_command = local_commands.get(command_name)
        short_description = description if len(description) <= 120 else description[:117] + "..."
        line = f"`/{command_name}` — {short_description}"
        if local_command and getattr(local_command.callback, "__checkin_admin_command__", False):
            admin_commands.append(line)
        else:
            user_commands.append(line)

    user_messages = chunk_lines(
        user_commands,
        prefix="**Checkin Bot Commands**\n**User Commands**",
    )
    has_admin_perms = bool(
        interaction.guild
        and getattr(getattr(interaction.user, "guild_permissions", None), "administrator", False)
    )
    admin_messages = (
        chunk_lines(admin_commands, prefix="**Admin Commands**")
        if has_admin_perms and admin_commands
        else []
    )

    await interaction.response.send_message(user_messages[0], ephemeral=True)
    for message in user_messages[1:] + admin_messages:
        await interaction.followup.send(message, ephemeral=True)

@tree.command(name="setstartdate", description="ADMIN: Set the event start date (YYYY-MM-DD)")
@app_commands.describe(date="Start date in YYYY-MM-DD format (example: 2026-09-05")
@admin_only()
async def setstartdate(interaction: discord.Interaction, date: str):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message(
            "Wrong format. Use YYYY-MM-DD (example: 2026-09-05)", ephemeral=True
        )
        return
    changed = set_start_date(date)
    message = f"Event start date set to **{date}** (Day 1)."
    if changed:
        message += " New check-ins will now be tracked for this event."
    await interaction.response.send_message(
        message, ephemeral=True
    )

@tree.command(name="resetuser", description="ADMIN: Reset one user's current event progress")
@app_commands.describe(member="The member whose current event check-ins should be cleared")
@admin_only()
async def resetuser(interaction: discord.Interaction, member: discord.Member):
    event_start = get_event_start_key()
    if not event_start:
        await interaction.response.send_message(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return

    removed = clear_user_checkins(member.id, event_start)
    await interaction.response.send_message(
        f"Reset **{member.display_name}** for event **{event_start}**. "
        f"Removed **{removed}** check-ins.",
        ephemeral=True,
    )

@tree.command(name="resettoday", description="ADMIN: Reset today's check-ins for everyone")
@admin_only()
async def resettoday(interaction: discord.Interaction):
    day = get_current_event_day()
    event_start = get_event_start_key()
    if day is None or not event_start:
        await interaction.response.send_message(
            "No active daily check-in is available to reset.",
            ephemeral=True,
        )
        return

    removed = clear_day_checkins(day, event_start)
    delete_setting(get_daily_close_key(event_start, day))
    delete_setting("last_winners:daily")
    await interaction.response.send_message(
        f"Reset Day {day} for event **{event_start}**. "
        f"Removed **{removed}** check-ins and reopened today's check-in.",
        ephemeral=True,
    )

@tree.command(name="resetevent", description="ADMIN: Reset the current weekly event to zero")
@admin_only()
async def resetevent(interaction: discord.Interaction):
    event_start = get_event_start_key()
    if not event_start:
        await interaction.response.send_message(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return

    removed = clear_event_checkins(event_start)
    delete_settings_with_prefix(f"daily_closed:{event_start}:")
    delete_setting("last_winners:daily")
    delete_setting("last_winners:final")
    await interaction.response.send_message(
        f"Reset the current event **{event_start}** to zero. "
        f"Removed **{removed}** check-ins.",
        ephemeral=True,
    )

@tree.command(name="enddaily", description="ADMIN: Close today's daily check-in without resetting the event")
@admin_only()
async def enddaily(interaction: discord.Interaction):
    day = get_current_event_day()
    event_start = get_event_start_key()
    if day is None or not event_start:
        await interaction.response.send_message(
            "No active daily check-in is available to close.",
            ephemeral=True,
        )
        return
    if is_daily_checkin_closed(day, event_start):
        await interaction.response.send_message(
            f"Day {day} is already closed for event **{event_start}**.",
            ephemeral=True,
        )
        return

    close_daily_checkin(day, event_start)
    await interaction.response.send_message(
        f"Day {day} is now closed for event **{event_start}**. "
        "Weekly progress was not reset.",
        ephemeral=True,
    )

@tree.command(name="dailydraw", description="ADMIN: Draw 1 Daily Lucky Star winner")
@admin_only()
async def dailydraw(interaction: discord.Interaction):
    day = get_current_event_day()
    event_start = get_event_start_key()
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
    c.execute(
        """
        SELECT user_id
        FROM checkins
        WHERE event_day = ? AND event_start = ?
        """,
        (day, event_start),
    )
    users = [row["user_id"] for row in c.fetchall()]
    conn.close()
    if not users:
        await interaction.followup.send("No one checked in today.", ephemeral=True)
        return
    winner_id = random.choice(users)
    winner = await bot.fetch_user(winner_id)
    store_last_winners(
        "daily",
        [{"user_id": winner_id, "prize": "1 SC"}],
        event_start=event_start,
        day=day,
    )
    await interaction.followup.send(
        f" **Daily Lucky Star Winner (Day {day})** \n"
        f"Congratulations {winner.mention}!\n"
        f"You won **1 SC**!"
    )

@tree.command(name="finaldraw", description="ADMIN: Draw the Final Lucky Draw winners (only players with 7/7)")
@admin_only()
async def finaldraw(interaction: discord.Interaction):
    # Defer immediately: this command can fetch up to 14 users sequentially,
    # which will blow past Discord's 3-second interaction deadline.
    await interaction.response.defer()
    event_start = get_event_start_key()
    if not event_start:
        await interaction.followup.send(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return
    conn = get_db()
    c = conn.cursor()
    # Get users who have all 7 days
    c.execute("""
    SELECT user_id FROM checkins
    WHERE event_start = ? AND event_day BETWEEN 1 AND 7
    GROUP BY user_id
    HAVING COUNT(DISTINCT event_day) = 7
    """, (event_start,))
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
    winners_payload = []
    index = 0
    for prize_name, count in prizes:
        for _ in range(count):
            if index >= len(users):
                break
            uid = users[index]
            member = await bot.fetch_user(uid)
            results.append(f"**{prize_name}** → {member.mention}")
            winners_payload.append({"user_id": uid, "prize": prize_name})
            index += 1
    store_last_winners(
        "final",
        winners_payload,
        event_start=event_start,
    )
    message = " **FINAL LUCKY DRAW WINNERS** \n\n" + "\n".join(results)
    await interaction.followup.send(message)

@tree.command(name="eligible", description="ADMIN: Show how many players have 7/7")
@admin_only()
async def eligible(interaction: discord.Interaction):
    event_start = get_event_start_key()
    if not event_start:
        await interaction.response.send_message(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    SELECT COUNT(*) as cnt FROM (
    SELECT user_id FROM checkins
    WHERE event_start = ? AND event_day BETWEEN 1 AND 7
    GROUP BY user_id
    HAVING COUNT(DISTINCT event_day) = 7
    )
    """, (event_start,))
    count = c.fetchone()["cnt"]
    conn.close()
    await interaction.response.send_message(
        f"Players with 7/7: **{count}**", ephemeral=True
    )

@tree.command(name="notifywinners", description="ADMIN: DM the most recent daily or final winners")
@app_commands.describe(
    draw_type="Choose 'daily' or 'final'",
    custom_message="Optional extra message to include in the DM",
)
@admin_only()
async def notifywinners(
    interaction: discord.Interaction,
    draw_type: str,
    custom_message: str | None = None,
):
    normalized = draw_type.lower().strip()
    if normalized not in {"daily", "final"}:
        await interaction.response.send_message(
            "Draw type must be `daily` or `final`.",
            ephemeral=True,
        )
        return

    payload = load_last_winners(normalized)
    if not payload or not payload.get("winners"):
        await interaction.response.send_message(
            f"No stored {normalized} winners were found yet.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    sent_count = 0
    failed_count = 0
    for winner_info in payload["winners"]:
        try:
            winner = await bot.fetch_user(int(winner_info["user_id"]))
            await winner.send(
                build_winner_dm(
                    normalized,
                    winner_info,
                    payload,
                    custom_message=custom_message,
                )
            )
            sent_count += 1
        except Exception:
            failed_count += 1

    await interaction.followup.send(
        f"Winner notifications sent: **{sent_count}**. Failed: **{failed_count}**.",
        ephemeral=True,
    )

@tree.command(name="todaycheckins", description="ADMIN: List today's checked-in players")
@admin_only()
async def todaycheckins(interaction: discord.Interaction):
    day = get_current_event_day()
    event_start = get_event_start_key()
    if day is None:
        await interaction.response.send_message(
            "Event is not active today.", ephemeral=True
        )
        return

    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id
        FROM checkins
        WHERE event_day = ? AND event_start = ?
        ORDER BY user_id
        """,
        (day, event_start),
    )
    users = [f"<@{row['user_id']}>" for row in c.fetchall()]
    conn.close()

    if not users:
        await interaction.response.send_message(
            f"No one has checked in for Day {day} yet.",
            ephemeral=True,
        )
        return
    messages = chunk_lines(
        users,
        prefix=f"**Day {day} check-ins ({len(users)})**",
    )
    await interaction.response.send_message(messages[0], ephemeral=True)
    for message in messages[1:]:
        await interaction.followup.send(message, ephemeral=True)

@tree.command(name="masterreset", description="ADMIN: Clear all check-ins and settings")
@app_commands.describe(confirm="Type MASTER RESET to confirm")
@admin_only()
async def masterreset(interaction: discord.Interaction, confirm: str):
    if confirm != "MASTER RESET":
        await interaction.response.send_message(
            "Confirmation text must be exactly `MASTER RESET`.",
            ephemeral=True,
        )
        return

    master_reset_data()
    await interaction.response.send_message(
        "Master reset complete. All events, check-ins, winners, and settings were cleared.",
        ephemeral=True,
    )

@tree.command(name="setupcheckinpost", description="ADMIN: Post a check-in setup message in this channel")
@admin_only()
async def setupcheckinpost(interaction: discord.Interaction):
    start = get_start_date()
    day = get_current_event_day()
    if not start:
        await interaction.response.send_message(
            get_start_date_error_message(),
            ephemeral=True,
        )
        return

    lines = [
        "## ✅ Check-in Event",
        f"Event start date: **{start.isoformat()}**",
    ]
    if day is None:
        lines.append("The 7-day event is not active right now.")
    else:
        lines.append(f"Current day: **Day {day}/7**")
        lines.append(
            f"Today's check-in is **{'closed' if is_daily_checkin_closed(day) else 'open'}**."
        )
    lines.extend(
        [
            "",
            "Use these commands:",
            "- `/checkin` — check in for today",
            "- `/progress` — see your progress",
            "- `/status` — see event status",
            "- `/leaderboard` — see top check-ins",
            "- `/commands` — see all commands",
        ]
    )
    await interaction.channel.send("\n".join(lines))
    await interaction.response.send_message(
        "Posted the check-in setup message in this channel.",
        ephemeral=True,
    )

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
    else:
        raise error

for command in (
    setstartdate,
    resetuser,
    resettoday,
    resetevent,
    enddaily,
    dailydraw,
    finaldraw,
    eligible,
    notifywinners,
    todaycheckins,
    masterreset,
    setupcheckinpost,
):
    command.error(admin_error)

def main():
    if not TOKEN:
        sys.exit(
            "ERROR: DISCORD_TOKEN is not set. "
            "Add it in Railway → your service → Variables (or a local .env file)."
        )
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
