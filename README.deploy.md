This repository can be deployed to Railway as a Worker (Discord bot).

Railway checklist
- Service type: Worker (Discord bots don’t need a public PORT).
- Required env vars: DISCORD_TOKEN (add any others your bot needs, e.g. DB_PATH if you override, SENTRY_DSN).
- Persistent DB: create a Railway Volume and mount it to /data. Set DB_PATH=/data/checkins.db to persist the sqlite DB.
- Build: the repo includes a Dockerfile (Python 3.11) that runs bot.py. Railway will auto-build the Docker image from the Dockerfile.
- Steps:
  1. Connect GitHub → select this repo and choose branch railway/deploy (or main).
  2. Configure environment variables in Railway (DISCORD_TOKEN, DB_PATH if using a volume).
  3. Set service type: Worker.
  4. Deploy and check logs for startup messages ("Bot is online as ..." and "Using database at: ...").

Notes
- The bot requires DISCORD_TOKEN. If DISCORD_TOKEN is missing, the process will exit on start.
- To persist checkins across restarts, attach a volume and set DB_PATH=/data/checkins.db.
- The repo already includes a Procfile (worker: python3 bot.py) if you prefer to let Railway run without Docker.
