// src/giveaway_commands.js
// Added immediate run-draw command: /giveaway_run_draw

const { dailyCheckinMessage, weeklyDrawAnnouncement } = require('./messages');

// ... existing code above remains unchanged. We'll append the new handler logic for the run_draw command.

// Insert this function at the end of module (below existing exports/handlers)

async function runWeeklyDraw(db, client, interaction, giveawayId = null) {
  // If giveawayId is provided, compute winners for that giveaway window.
  // Otherwise run the standard Thu->Wed weekly draw using current date.
  if (giveawayId) {
    const row = await db.get(`SELECT * FROM giveaways WHERE id = ?`, giveawayId);
    if (!row) {
      await interaction.reply({ content: `Giveaway ${giveawayId} not found`, ephemeral: true });
      return;
    }
    const startIso = row.start_iso || (row.start_date ? `${row.start_date}T00:00` : null);
    const endIso = row.end_iso || (row.end_date ? `${row.end_date}T23:59` : null);
    if (!startIso || !endIso) {
      await interaction.reply({ content: `Giveaway ${giveawayId} does not have a valid start/end window set`, ephemeral: true });
      return;
    }

    const winners = await computeWinners(db, startIso, endIso, 3);
    const winnersText = winners.map((id, i) => `• <@${id}> — Prize ${i + 1}`).join('\n') || 'No eligible winners.';
    const channel = await client.channels.fetch(row.channel_id).catch(() => null);
    if (channel) {
      await channel.send(`(Manual) Giveaway ${row.id} draw complete. Winners:\n${winnersText}`).catch(() => null);
    }
    await db.run(`UPDATE giveaways SET status = 'ended' WHERE id = ?`, giveawayId);
    await logAction(db, giveawayId, 'manual_draw', interaction.user.id);
    await interaction.reply({ content: `Manual draw complete for giveaway ${giveawayId}`, ephemeral: true });
    return;
  }

  // Otherwise do standard Thu->Wed weekly draw
  const now = new Date();
  const tzDate = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
  const endDate = tzDate.toISOString().split('T')[0];
  const start = new Date(tzDate);
  start.setDate(start.getDate() - 6);
  const startDate = start.toISOString().split('T')[0];

  const rows = await db.all(`SELECT user_id FROM checkins WHERE date BETWEEN ? AND ? GROUP BY user_id HAVING COUNT(DISTINCT date) = 7`, startDate, endDate);
  const userIds = rows.map(r => r.user_id);
  const winners = [];
  const copy = userIds.slice();
  while (winners.length < Math.min(3, copy.length)) {
    const idx = Math.floor(Math.random() * copy.length);
    winners.push(copy.splice(idx, 1)[0]);
  }

  const winnersText = winners.map((id, i) => `• <@${id}> — Prize ${i + 1}`).join('\n') || 'No eligible winners this week.';
  const last = await db.get(`SELECT channel_id FROM daily_messages ORDER BY date DESC LIMIT 1`);
  const channelId = last ? last.channel_id : process.env.CHECKIN_CHANNEL_ID;
  const channel = channelId ? await client.channels.fetch(channelId).catch(() => null) : null;
  if (channel) {
    await channel.send(`(Manual) Weekly Final Draw — Winners\nThis draw covers check‑ins from Thursday ${startDate} through Wednesday ${endDate} (Thursday = Day 1).\n${winnersText}`).catch(() => null);
  }
  await logAction(db, null, 'manual_weekly_draw', interaction.user.id);
  await interaction.reply({ content: 'Manual weekly draw complete.', ephemeral: true });
}

// Update the ensureCommandsRegistered to include the new command
// Add to the commands array when registering:
// {
//   name: 'giveaway_run_draw',
//   description: 'Run a giveaway draw immediately (admin)',
//   options: [ { name: 'id', type: 4, description: 'Giveaway id (optional)', required: false } ]
// }

// And in handleInteraction, add:
// else if (name === 'giveaway_run_draw') { ... }

// For brevity, we add the handling inside the exported handleInteraction by checking for the command.

module.exports.runWeeklyDraw = runWeeklyDraw;
