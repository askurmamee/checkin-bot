# Pinning integration guide

This file provides a ready-to-paste code snippet and integration notes for pinning the daily check-in message and unpinning the previous day's message. The snippet is intentionally minimal and assumes your existing DB layer exposes functions to read/write the `daily_messages` table (see notes below).

What it does
- Pins the newly posted daily check-in message.
- Looks up the previous day's recorded message_id from the `daily_messages` table and, if found and different, attempts to unpin that message.

Integration notes
- The snippet below expects you to have a DB API with at least:
  - `getLatestDailyMessage()` -> { date, channel_id, message_id } | null
  - `saveDailyMessage(date, channel_id, message_id)` -> void
- Replace `db.getLatestDailyMessage()` and `db.saveDailyMessage(...)` with your actual DB calls.
- This snippet uses discord.js v13+/v14 message.pin() / channel.messages.fetch(). If your project uses a different version, adjust accordingly.

Example (Node.js, CommonJS):

// src/pinning_example.js
async function pinNewDailyMessage(client, db, channelId, newMessage) {
  try {
    // Pin the new message
    await newMessage.pin();
  } catch (err) {
    console.warn('Failed to pin new daily message:', err);
    // continue — pinning is optional
  }

  // Lookup previously recorded daily message (latest one)
  const previous = await db.getLatestDailyMessage(); // implement in your DB layer

  if (previous && previous.message_id && previous.message_id !== newMessage.id) {
    try {
      const channel = await client.channels.fetch(previous.channel_id);
      if (channel && channel.isText()) {
        // Fetch the previous message and unpin it
        const prevMsg = await channel.messages.fetch(previous.message_id);
        if (prevMsg && prevMsg.pinned) {
          await prevMsg.unpin();
        }
      }
    } catch (err) {
      console.warn('Failed to unpin previous daily message:', err);
      // not fatal
    }
  }

  // Save the new message record (so future runs can unpin it)
  await db.saveDailyMessage(newMessage.createdAt.toISOString().split('T')[0], channelId, newMessage.id);
}

Module exports

module.exports = { pinNewDailyMessage };

Notes on DB functions (implement these in your existing DB layer)
- getLatestDailyMessage(): should return the newest row from daily_messages (ORDER BY date DESC LIMIT 1) with fields { date, channel_id, message_id }
- saveDailyMessage(date, channel_id, message_id): insert or replace the row for the given date in daily_messages

Error handling
- Pin/unpin failures are non-fatal — the snippet logs warnings and proceeds. Ensure the bot has the Manage Messages or Pin Messages permission as appropriate.

Permissions required
- The bot needs the following channel permissions to manage pins:
  - View Channel
  - Send Messages
  - Read Message History
  - Add Reactions
  - Manage Messages (to unpin messages)
  - Manage Channels is NOT required
