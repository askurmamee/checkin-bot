## Pinning option

This branch includes an optional pinning integration. If you enable pinning, the bot will:
- Pin the newly posted daily check-in message each night.
- Unpin the previous day's check-in message (if found) to keep the channel tidy.

To enable pinning, integrate the snippet in docs/pinning_integration.md with your scheduler where the bot posts the daily message. You'll need to implement two simple DB helpers (getLatestDailyMessage and saveDailyMessage) that operate on the `daily_messages` table so the pin/unpin logic can find the previous message.

Permissions: the bot will need Manage Messages in the check-in channel to unpin previous messages.
