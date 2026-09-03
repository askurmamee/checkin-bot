## Pinning option

This branch includes an optional pinning integration. When enabled, the bot automatically manages pins on your daily check-in messages to keep your channel organized.

### Features

- **Pins new messages**: Automatically pins the daily check-in message each night
- **Unpins old messages**: Removes the pin from the previous day's check-in (if found) to keep the channel tidy
- **Error resilient**: Pin/unpin failures don't crash the bot — they log a warning and continue

### Prerequisites

Before enabling pinning, ensure:

1. **Database table exists**: You need a `daily_messages` table with columns:
   - `date` (string or date)
   - `channel_id` (string)
   - `message_id` (string)

2. **Bot permissions**: The bot must have these channel permissions:
   - View Channel
   - Send Messages
   - Read Message History
   - Manage Messages (required to unpin previous messages)

3. **Database API**: You'll implement two simple DB helpers:
   - `getLatestDailyMessage()` → returns `{ date, channel_id, message_id }` or `null`
   - `saveDailyMessage(date, channel_id, message_id)` → saves/updates the record

### How to enable pinning

1. **Review the integration code**: Open [`docs/pinning_integration.md`](./docs/pinning_integration.md) to see the full example with error handling.

2. **Implement DB helpers**: Add the two database functions above to your database layer. See the integration guide for implementation notes.

3. **Integrate with your scheduler**: In the code that posts the daily check-in message, call the pinning function:
   ```javascript
   const { pinNewDailyMessage } = require('./src/pinning_example');
   
   // After posting the new daily message:
   await pinNewDailyMessage(client, db, channelId, newMessage);
   ```

4. **Test**: Run the bot and verify:
   - The new check-in message is pinned
   - The previous day's pin is removed (if one exists)
   - No permission errors in the logs

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Missing permissions" error | Ensure the bot has **Manage Messages** permission in the check-in channel. |
| Previous message not unpinning | Verify the `getLatestDailyMessage()` function returns the correct message ID. Check that the message still exists in the channel. |
| Messages not pinning at all | Check bot permissions and confirm `newMessage.pin()` is being called with an actual Discord message object. |
| Database helpers not found | Ensure `db.getLatestDailyMessage()` and `db.saveDailyMessage()` are properly exported from your DB layer. |

### Questions?

See [`docs/pinning_integration.md`](./docs/pinning_integration.md) for the full code example, detailed implementation notes, and error handling patterns.
