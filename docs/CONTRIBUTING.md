# Checkin Bot Development Guide

## Project Structure

```
checkin-bot/
├── bot.py                      — Main bot application
├── requirements.txt            — Python dependencies
├── .env.example                — Environment variable template
├── .gitignore                  — Git ignore rules
├── Dockerfile                  — Docker container config
├── Procfile                    — Heroku/Railway deployment config
├── runtime.txt                 — Python runtime version
├── README.md                   — Main documentation
├── README_PINNING.md           — Pinning feature guide
├── docs/
│   ├── pinning_integration.md  — Detailed pinning implementation
│   └── CONTRIBUTING.md         — This file
├── src/
│   └── pinning.py              — Optional pinning module (if enabled)
└── (legacy files - not used)
    ├── register_guild_commands.js
    └── test_reaction_post.js
```

## Local Development

### 1. Clone and Setup

```bash
git clone https://github.com/askurmamee/checkin-bot.git
cd checkin-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

```bash
cp .env.example .env
# Edit .env and add your DISCORD_TOKEN
cat .env
```

### 3. Run Locally

```bash
python bot.py
```

You should see:
```
Bot is online as YourBotName#1234
Using database at: /path/to/checkins.db
Synced X commands
```

## Testing

### Manual Testing Checklist

- [ ] Bot comes online and syncs commands
- [ ] `/setstartdate 2026-09-05` works (admin only)
- [ ] `/checkin` works and saves to database
- [ ] Reacting with 👍 on the daily post records check-in
- [ ] `/progress` shows correct count
- [ ] `/dailydraw` draws a winner
- [ ] `/eligible` shows player count
- [ ] `/finaldraw` works with 14+ players
- [ ] `/totalcount` shows total check-ins
- [ ] `/resetmembers` resets all check-ins
- [ ] `/masterreset` clears event data
- [ ] `/editmember` updates one member's check-ins
- [ ] `/postdailycheckin` posts a daily message with 👍

### Database Testing

```bash
# Connect to SQLite database
sqlite3 checkins.db

# Check tables
.tables

# View checkins
SELECT * FROM checkins;

# View settings
SELECT * FROM settings;
```

## Code Style

- Use **snake_case** for function names
- Use **UPPER_CASE** for constants
- Add docstrings to async functions
- Keep functions under 50 lines when possible
- Use type hints where applicable

## Adding Features

### Adding a New Slash Command

1. Create the command function in `bot.py`:
```python
@tree.command(name="mycommand", description="What this does")
@app_commands.checks.has_permissions(administrator=True)
async def mycommand(interaction: discord.Interaction):
    await interaction.response.send_message("Done!", ephemeral=True)
```

2. Add error handling if needed:
```python
@mycommand.error
async def mycommand_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Admin required", ephemeral=True)
```

3. Restart the bot—commands sync automatically

### Adding Database Tables

In `init_db()`:
```python
c.execute("""
CREATE TABLE IF NOT EXISTS your_table (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    value TEXT
)
""")
```

## Deployment

### Railway Deployment

1. Push to GitHub
2. Create Railway project
3. Set environment variables:
   - `DISCORD_TOKEN` — your bot token
   - `DB_PATH` — `/data/checkins.db`
4. Attach a volume to `/data`
5. Deploy!

### Local Production (Systemd)

```bash
# Create /etc/systemd/system/checkin-bot.service
[Unit]
Description=Checkin Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/path/to/checkin-bot
Environment="DISCORD_TOKEN=your_token"
Environment="DB_PATH=/data/checkins.db"
ExecStart=/path/to/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl start checkin-bot
sudo systemctl enable checkin-bot
sudo systemctl logs checkin-bot -f
```

## Troubleshooting

### Bot offline
- Check `DISCORD_TOKEN` is set correctly
- Verify bot is in the server with appropriate intents
- Check console for error messages

### Commands not appearing
- Bot must have `applications.commands` OAuth2 scope
- Restart bot—commands sync on startup
- Check bot has "Use Slash Commands" permission

### Database locked
- Bot uses WAL mode to prevent this
- If persistent, delete `checkins.db-shm` and `checkins.db-wal`
- Restart bot

## Future Improvements

- [ ] Move hardcoded timezone to environment variable
- [ ] Add command logging to database
- [ ] Add user statistics/leaderboards
- [ ] Create web dashboard for stats
- [x] Automated daily message posting at midnight (Asia/Shanghai)
- [ ] Implement pinning integration (see `docs/pinning_integration.md`)

## Questions or Issues?

Check the main README or open an issue on GitHub!
