// src/reactions.js
// Reaction and message moderation handlers to enforce reaction-only check-ins.
const CHECK_EMOJI = '✅';

function attachReactionHandlers(client, db) {
  // Helper to determine if a message is a tracked daily message
  async function isTrackedMessage(message) {
    try {
      const row = await db.get(`SELECT date FROM daily_messages WHERE message_id = ?`, message.id);
      return row ? row.date : null;
    } catch (err) {
      console.error('isTrackedMessage error', err);
      return null;
    }
  }

  client.on('messageReactionAdd', async (reaction, user) => {
    try {
      if (user.bot) return;
      if (reaction.partial) await reaction.fetch();
      const message = reaction.message;

      const date = await isTrackedMessage(message);
      if (!date) return; // not a tracked daily message

      if (reaction.emoji.name !== CHECK_EMOJI) {
        // remove incorrect reaction and DM the user
        try {
          await reaction.users.remove(user.id).catch(() => null);
        } catch (e) { /* ignore */ }
        try {
          await user.send("Please use ✅ on the daily check-in message to check in. Other reactions don't count and have been removed.");
        } catch (e) { /* user may have DMs closed */ }
        return;
      }

      // correct emoji: record checkin
      await db.run(`INSERT OR IGNORE INTO checkins (user_id, date) VALUES (?, ?)`, user.id, date);
      console.log(`Recorded checkin for ${user.id} on ${date}`);
    } catch (err) {
      console.error('reaction add handler error', err);
    }
  });

  client.on('messageReactionRemove', async (reaction, user) => {
    try {
      if (user.bot) return;
      if (reaction.partial) await reaction.fetch();
      if (reaction.emoji.name !== CHECK_EMOJI) return;

      const date = await isTrackedMessage(reaction.message);
      if (!date) return;
      await db.run(`DELETE FROM checkins WHERE user_id = ? AND date = ?`, user.id, date);
      console.log(`Removed checkin for ${user.id} on ${date}`);
    } catch (err) {
      console.error('reaction remove handler error', err);
    }
  });

  // Enforce reaction-only channel: delete non-bot messages in the configured channel
  client.on('messageCreate', async (message) => {
    try {
      if (message.author.bot) return;

      const checkinChannelId = process.env.CHECKIN_CHANNEL_ID;
      const isCheckinChannel = checkinChannelId ? (message.channel.id === checkinChannelId) : (message.channel.name === 'daily-checkin');
      if (!isCheckinChannel) return;

      // If the message is the bot's daily message (unlikely since author.bot is false), ignore
      // Delete the user's message and DM a gentle reminder
      await message.delete().catch(() => null);
      try {
        await message.author.send("Please do not post messages in the daily check-in channel. Use the ✅ reaction on the bot's daily check-in message to mark your check-in.");
      } catch (e) { /* ignore if DMs closed */ }
    } catch (err) {
      console.error('messageCreate moderation error', err);
    }
  });
}

module.exports = { attachReactionHandlers };
