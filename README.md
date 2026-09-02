# checkin-bot

Small Discord check-in bot.

Deployment notes (Railway)

- Service type: Worker (this runs as a background worker). The repository already includes a Procfile: `worker: python3 bot.py` which Railway will use.

- Environment variables (Railway → Service → Variables):
  - DISCORD_TOKEN = <your bot token>
  - (optional) DB_PATH = /data/checkins.db — set this if you add a persistent volume.

- Persistent database (recommended):
  - Add a Railway Volume and mount it at `/data`.
  - If you do, set DB_PATH=/data/checkins.db to persist check-ins across deployments.

- Build & Start:
  - Railway will install dependencies from requirements.txt and run the Procfile worker command.
  - Logs will show: `Bot is online as ...` and `Using database at: ...` when ready.

Local testing

1. Create a `.env` file containing:
```
DISCORD_TOKEN=your_token_here
```
2. Install deps and run locally:
```
pip install -r requirements.txt
python3 bot.py
```

If you want, I can adjust more files or remove the Dockerfile if you prefer Railway's build.
