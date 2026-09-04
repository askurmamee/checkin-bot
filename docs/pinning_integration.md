# Pinning Integration for Checkin Bot (Python)

This guide explains how to add automatic message pinning to your Discord check-in bot.

## What It Does

When enabled, the bot will:
- Pin the daily check-in message each day
- Unpin the previous day's message to keep the channel tidy

## Prerequisites

1. **Database table**: You need a `daily_messages` table in your SQLite database:
   ```sql
   CREATE TABLE IF NOT EXISTS daily_messages (
       date TEXT PRIMARY KEY,
       channel_id TEXT,
       message_id TEXT
   );
   ```

2. **Bot permissions**: The bot must have these channel permissions:
   - View Channel
   - Send Messages
   - Read Message History
   - **Manage Messages** (required to unpin messages)

3. **discord.py version**: 2.3.0 or higher (already in requirements.txt)

## Implementation

### Step 1: Create a pinning helper module

Create a new file `src/pinning.py`:

```python
# src/pinning.py
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def get_latest_daily_message(db_path):
    """Get the most recent daily message record from the database."""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, channel_id, message_id FROM daily_messages ORDER BY date DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching latest daily message: {e}")
        return None

def save_daily_message(db_path, date, channel_id, message_id):
    """Save or update a daily message record."""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO daily_messages (date, channel_id, message_id) VALUES (?, ?, ?)",
            (date, channel_id, message_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"Saved daily message for {date}: {message_id}")
    except Exception as e:
        logger.error(f"Error saving daily message: {e}")

async def pin_new_daily_message(bot, db_path, channel, new_message):
    """
    Pin the new daily message and unpin the previous day's message.
    
    Args:
        bot: Discord bot instance
        db_path: Path to SQLite database
        channel: Discord channel object
        new_message: The newly posted message to pin
    """
    try:
        # Pin the new message
        await new_message.pin()
        logger.info(f"Pinned message {new_message.id}")
    except Exception as e:
        logger.warning(f"Failed to pin new message: {e}")

    # Get the previous day's message record
    previous = get_latest_daily_message(db_path)
    
    if previous and previous.get("message_id") and previous["message_id"] != str(new_message.id):
        try:
            # Fetch the channel if needed
            if channel.id != int(previous["channel_id"]):
                channel = await bot.fetch_channel(int(previous["channel_id"]))
            
            # Try to unpin the previous message
            prev_msg = await channel.fetch_message(int(previous["message_id"]))
            if prev_msg and prev_msg.pinned:
                await prev_msg.unpin()
                logger.info(f"Unpinned previous message {previous['message_id']}")
        except Exception as e:
            logger.warning(f"Failed to unpin previous message: {e}")

    # Save the new message record
    today = datetime.now().strftime("%Y-%m-%d")
    save_daily_message(db_path, today, str(channel.id), str(new_message.id))
```

### Step 2: Initialize the database table

Add this to your `bot.py` in the `init_db()` function:

```python
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
    # ADD THIS:
    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_messages (
    date TEXT PRIMARY KEY,
    channel_id TEXT,
    message_id TEXT
    )
    """)
    conn.commit()
    conn.close()
```

### Step 3: Call the pinning function

In your `bot.py`, after posting the daily check-in message, call the pinning function:

```python
from src.pinning import pin_new_daily_message

# After creating and sending the daily check-in message:
await pin_new_daily_message(bot, DB_PATH, channel, new_message)
```

### Step 4: Error Handling

The pinning function is non-fatal—if it fails, it logs a warning and continues. The bot won't crash if:
- The previous message was deleted
- The bot lost permissions
- The database is temporarily unavailable

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot pin message" | Ensure bot has **Manage Messages** permission in the channel |
| "Message not found" | The previous message may have been deleted; this is expected |
| "Permission denied" | Check bot permissions and role hierarchy |
| Database errors | Verify the `daily_messages` table exists (run Step 2) |

## Testing

After implementation, test manually:

```python
# In bot.py, in a test command:
@tree.command(name="test_pin", description="Test message pinning")
async def test_pin(interaction: discord.Interaction):
    await interaction.response.defer()
    channel = interaction.channel
    msg = await channel.send("Test pin message")
    
    from src.pinning import pin_new_daily_message
    await pin_new_daily_message(bot, DB_PATH, channel, msg)
    
    await interaction.followup.send("Pin test complete!")
```

## Questions?

See the main README for general bot setup and configuration.
