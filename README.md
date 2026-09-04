# Checkin Bot

A Discord bot for managing check-in events with daily and final draws. Built with discord.py.

## Features

- **Daily Check-in**: Users use `/checkin` or react with 👍 on the daily post
- **Daily Lucky Draw**: Admin can draw 1 random winner from today's check-ins
- **Final Lucky Draw**: Admin draws winners from players with 7/7 check-ins (1x 10 SC, 3x 5 SC, 10x 1 SC)
- **Progress Tracking**: Users can see their check-in progress anytime
- **Automatic Midnight Posts**: The bot can auto-post the next day's check-in message in Asia/Shanghai time

## Quick Start

### Prerequisites

- Python 3.11+
- A Discord bot token (create one at [Discord Developer Portal](https://discord.com/developers/applications))
- Administrator access to a Discord server for testing

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/askurmamee/checkin-bot.git
   cd checkin-bot
   ```

2. **Create a virtual environment** (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and add your Discord bot token:
   ```
   DISCORD_TOKEN=your_bot_token_here
   DB_PATH=checkins.db
   ```

5. **Run the bot**:
   ```bash
   python bot.py
   ```

### Deployment to Railway

1. Push your code to GitHub
2. Create a new project on [Railway](https://railway.app)
3. Connect your GitHub repository
4. Add environment variables in Railway dashboard:
   - `DISCORD_TOKEN` — your Discord bot token
   - `DB_PATH` — set to `/data/checkins.db` (requires volume mount)
   - `CHECKIN_CHANNEL_ID` — optional fixed channel for the daily auto-post
   - `DISCORD_GUILD_ID` — optional guild ID for fast guild command sync
5. Attach a volume to `/data` for persistent database storage
6. Deploy!

For more details, see [Railway docs](https://docs.railway.app/guides/projects).

## Commands

### User Commands

- **`/checkin`** — Check in for the current day
- **`/progress`** — View your check-in progress (X/7 days)

### Admin Commands

- **`/setstartdate <YYYY-MM-DD>`** — Set the event start date (requires Administrator)
- **`/dailydraw`** — Draw 1 random winner from today's check-ins (requires Administrator)
- **`/finaldraw`** — Draw winners for players with 7/7 check-ins (requires Administrator, minimum 14 eligible players)
- **`/eligible`** — See how many players have completed 7/7 (requires Administrator)
- **`/totalcount`** — Show the total number of check-ins across all members (requires Administrator)
- **`/resetmembers`** — Clear all member check-ins (requires Administrator)
- **`/masterreset`** — Clear check-ins, settings, and tracked daily posts (requires Administrator)
- **`/editmember <user> <value>`** — Adjust a member's total by a signed number such as `+2` or `-1` (requires Administrator)
- **`/postdailycheckin`** — Manually post today's 👍 check-in message and save that channel for auto-posts (requires Administrator)

## Database

The bot uses SQLite3. Three tables are created automatically:

### `checkins`
```
user_id (INTEGER)    — Discord user ID
event_day (INTEGER)  — Day of the event (1-7)
PRIMARY KEY (user_id, event_day)
```

### `settings`
```
key (TEXT)   — Setting name
value (TEXT) — Setting value
PRIMARY KEY (key)
```

Currently stores:
- `start_date` — The event start date in YYYY-MM-DD format
- `checkin_channel_id` — The preferred channel for manual and midnight daily posts

## Configuration

### Environment Variables

- `DISCORD_TOKEN` (required) — Your Discord bot token
- `DB_PATH` (optional, default: `checkins.db`) — Path to SQLite database
  - On Railway with volume: use `/data/checkins.db`
  - Locally: use relative path like `checkins.db`
- `CHECKIN_CHANNEL_ID` (optional) — Preferred channel for the midnight auto-post
- `DISCORD_GUILD_ID` (optional) — Guild ID to force an immediate guild sync in addition to the global sync

### Bot Permissions Required

Ensure the bot has these permissions in any channel where it operates:

- View Channel
- Send Messages
- Read Message History
- Add Reactions

### Timezone

The bot currently uses **Asia/Shanghai (UTC+8)** for event day calculations. To change this, edit line 15 in `bot.py`:

```python
TZ = ZoneInfo("Asia/Shanghai")  # Change this to your preferred timezone
```

See [Python timezone docs](https://docs.python.org/3/library/zoneinfo.html) for available timezones.

## Architecture

### Database Connection

The bot uses SQLite3 with:
- **WAL mode**: Write-Ahead Logging to prevent "database is locked" errors
- **Timeouts**: 10-second connection timeout for concurrent access
- **Thread safety**: `check_same_thread=False` allows safe cross-thread usage

Each command opens its own connection to the database.

### Event Handling

The bot uses Discord slash commands (`app_commands`) for a modern user interface. On startup it validates that all 11 commands are loaded, syncs them globally, and also syncs them to `DISCORD_GUILD_ID` (or the only connected guild) for immediate availability when possible.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "DISCORD_TOKEN is not set" | Add your bot token to `.env` (local) or Railway Variables tab |
| "Event is not active" | Use `/setstartdate YYYY-MM-DD` to set the event start date |
| "Database is locked" errors | The bot uses WAL mode to mitigate this; if persistent, restart the bot |
| Bot doesn't respond to commands | Check bot has "Send Messages" permission and commands are synced (check console on startup) |
| Timezone seems wrong | Edit line 15 in `bot.py` to change the timezone |

## Development

### Running Tests

```bash
python test_reaction_post.js  # Test script (note: currently not integrated)
```

### Structure

```
.
├── bot.py                      — Main bot code
├── requirements.txt            — Python dependencies
├── Dockerfile                  — Container configuration
├── Procfile                    — Heroku deployment config
├── .env.example                — Environment variable template
├── register_guild_commands.js  — Legacy JavaScript (not used)
├── test_reaction_post.js       — Legacy JavaScript test (not used)
└── docs/
    ├── README_PINNING.md       — Optional pinning feature (future work)
    └── pinning_integration.md  — Pinning implementation guide (future work)
```

## Future Features

- **Pinning integration** — Automatically pin daily check-in messages (see `docs/README_PINNING.md`)
- **Leaderboards** — Show top check-in performers
- **Timezone selection** — Per-user timezone support

## Contributing

Feel free to open issues and pull requests!

## License

MIT (or add your preferred license)
