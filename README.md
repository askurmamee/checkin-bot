# Checkin Bot

A small Discord bot that implements /checkin and /stats using SQLite.

What changed in this branch
- Replaced blocking sqlite3 calls with aiosqlite (async) so DB operations don't block the event loop.
- Added basic logging and token validation.
- Added .env.example and updated requirements.

Quick start
1. Create a virtual environment and install dependencies:

   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt

2. Create a .env file with your Discord bot token (see .env.example):

   DISCORD_TOKEN=your_token_here

3. Run the bot locally:

   python3 bot.py

Notes
- The bot uses ZoneInfo("Asia/Shanghai") for timestamps — change TZ in bot.py if you want a different timezone.
- Procfile is provided for Heroku-style deployments (worker: python3 bot.py).

Inviting the bot
- Create an Application and Bot in the Discord Developer Portal.
- Enable "MESSAGE CONTENT INTENT" if you plan to read message content (this bot uses intents.message_content=True currently).
- Use an OAuth2 URL with scope=bot%20applications.commands and the permissions you need to invite the bot to a server.
