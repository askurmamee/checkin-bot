# Checkin Bot

(Documentation additions from feature/daily-checkins)

## Daily check-in messages

The bot posts a daily check-in message at 00:00 America/Chicago in the configured check-in channel. The message template is centralized in `src/messages.js` and reads:

```
Daily Check‑in — {YYYY‑MM‑DD}
React with ✅ to mark today's check‑in. This is reaction‑only — please don't send messages in this channel for check‑ins. Remove your ✅ if you need to undo your check‑in.
```

The bot immediately reacts with ✅ to the message and records the message_id in the `daily_messages` DB table so it can track reactions for that specific day.

### Configuration
- Default channel name: `daily-checkin` (the bot will search for a channel with this name).
- Optional environment variable: `CHECKIN_CHANNEL_ID` to force a specific channel id.
- Database path: `DB_PATH` (see your existing README for DB setup). For Railway, use `DB_PATH=/data/checkins.db` and attach a volume.

### Bot permissions required in the check-in channel
- View Channel, Send Messages, Read Message History, Add Reactions.
- (Optional) Manage Messages if you want the bot to remove reactions automatically at reset.

### Weekly final draw
- Runs Wednesday at 00:00 America/Chicago covering check-ins from Thursday → Wednesday (Thursday = Day 1).
- The announcement template is centralized in `src/messages.js` and includes the window and winner list.

---

This change centralizes the UI strings so they can be edited easily without touching scheduling or DB logic. Apply these templates where the bot constructs daily posts and final-draw announcements.
