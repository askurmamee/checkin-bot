// src/giveaway_commands.js
// Slash command handlers for scheduling, cancelling, updating, controlling giveaways, and auto-registering per-guild on start.
const { dailyCheckinMessage, weeklyDrawAnnouncement } = require('./messages');

// Command definitions (used for per-guild registration)
const COMMANDS = [
  {
    name: 'giveaway_start',
    description: 'Schedule a giveaway start date (YYYY-MM-DD)',
    options: [
      { name: 'date', type: 3, description: 'Start date (YYYY-MM-DD)', required: true },
      { name: 'end_date', type: 3, description: 'Optional end date (YYYY-MM-DD)', required: false },
      { name: 'prize', type: 3, description: 'Prize description', required: false },
    ],
  },
  {
    name: 'giveaway_cancel',
    description: 'Cancel a scheduled giveaway by id (or cancel next upcoming if omitted)',
    options: [ { name: 'id', type: 4, description: 'Giveaway id', required: false } ],
  },
  {
    name: 'giveaway_update',
    description: 'Update a scheduled giveaway times (id required)',
    options: [
      { name: 'id', type: 4, description: 'Giveaway id', required: true },
      { name: 'start_iso', type: 3, description: 'Start YYYY-MM-DDTHH:MM (America/Chicago)', required: false },
      { name: 'end_iso', type: 3, description: 'End YYYY-MM-DDTHH:MM (America/Chicago)', required: false },
    ],
  },
  {
    name: 'giveaway_control',
    description: 'Control a giveaway: startnow or endnow',
    options: [
      { name: 'id', type: 4, description: 'Giveaway id', required: true },
      { name: 'action', type: 3, description: 'startnow or endnow', required: true },
    ],
  },
  {
    name: 'giveaway_run_draw',
    description: 'Run a giveaway draw immediately (admin)',
    options: [ { name: 'id', type: 4, description: 'Giveaway id (optional)', required: false } ],
  },
];

async function computeWinners(db, startIso, endIso, maxWinners = 3) {
  const startDate = startIso.split('T')[0];
  const endDate = endIso.split('T')[0];
  const days = Math.round((new Date(endDate) - new Date(startDate)) / (24 * 3600 * 1000)) + 1;
  const rows = await db.all(`SELECT user_id FROM checkins WHERE date BETWEEN ? AND ? GROUP BY user_id HAVING COUNT(DISTINCT date) = ?`, startDate, endDate, days);
  const userIds = rows.map(r => r.user_id);
  const winners = [];
  const copy = userIds.slice();
  while (winners.length < Math.min(maxWinners, copy.length)) {
    const idx = Math.floor(Math.random() * copy.length);
    winners.push(copy.splice(idx, 1)[0]);
  }
  return winners;
}

function isAdminOrCreator(interaction, row) {
  const isAdmin = interaction.memberPermissions?.has('ManageGuild');
  const isCreator = row && row.creator_id && row.creator_id === interaction.user.id;
  return Boolean(isAdmin || isCreator);
}

async function logAction(db, giveawayId, action, userId) {
  try {
    await db.run(`INSERT INTO action_logs (giveaway_id, action, user_id) VALUES (?, ?, ?)`, giveawayId || null, action, userId);
  } catch (err) {
    console.error('Failed to log action', err);
  }
}

// Register commands per-guild when the client is ready. This ensures instant availability in guilds the bot is present in.
function ensureCommandsRegistered(client) {
  client.on('ready', async () => {
    try {
      // Register commands for each guild the bot is in
      for (const guild of client.guilds.cache.values()) {
        try {
          await guild.commands.set(COMMANDS);
          console.log(`Registered commands for guild ${guild.id}`);
        } catch (err) {
          console.error(`Failed to register commands for guild ${guild.id}`, err);
        }
      }
    } catch (err) {
      console.error('Error registering commands for guilds', err);
    }
  });
}

// Main interaction handler for all giveaway-related commands
async function handleInteraction(interaction, db, scheduler, client) {
  if (!interaction.isCommand()) return;
  const name = interaction.commandName;

  if (name === 'giveaway_start') {
    if (!interaction.memberPermissions?.has('ManageGuild')) {
      interaction.reply({ content: 'You do not have permission to schedule giveaways.', ephemeral: true });
      return;
    }

    const date = interaction.options.getString('date');
    const endDate = interaction.options.getString('end_date');
    const prize = interaction.options.getString('prize') || 'Prize';
    const channelId = interaction.channelId;
    const creatorId = interaction.user.id;

    try {
      const res = await db.run(
        `INSERT INTO giveaways (start_date, end_date, prize, channel_id, status, creator_id) VALUES (?, ?, ?, ?, 'scheduled', ?)` ,
        date, endDate || null, prize, channelId, creatorId
      );
      const id = res.lastID;
      await logAction(db, id, 'scheduled', interaction.user.id);
      interaction.reply({ content: `Giveaway scheduled (id: ${id}) to start on ${date}`, ephemeral: false });
      scheduler.checkDueGiveaways();
    } catch (err) {
      console.error('Error scheduling giveaway', err);
      interaction.reply({ content: 'Failed to schedule giveaway', ephemeral: true });
    }
    return;
  }

  if (name === 'giveaway_cancel') {
    if (!interaction.memberPermissions?.has('ManageGuild')) {
      interaction.reply({ content: 'You do not have permission to cancel giveaways.', ephemeral: true });
      return;
    }

    const id = interaction.options.getInteger('id');
    try {
      if (id) {
        const row = await db.get(`SELECT * FROM giveaways WHERE id = ?`, id);
        if (!row) {
          interaction.reply({ content: `Giveaway ${id} not found`, ephemeral: true });
          return;
        }
        if (!isAdminOrCreator(interaction, row)) {
          interaction.reply({ content: 'You are not authorized to cancel this giveaway.', ephemeral: true });
          return;
        }
        await db.run(`UPDATE giveaways SET status = 'canceled' WHERE id = ?`, id);
        await logAction(db, id, 'canceled', interaction.user.id);
        interaction.reply({ content: `Canceled giveaway ${id}`, ephemeral: false });
        scheduler.checkDueGiveaways();
      } else {
        const row = await db.get(`SELECT * FROM giveaways WHERE status = 'scheduled' ORDER BY start_date LIMIT 1`);
        if (!row) {
          interaction.reply({ content: 'No upcoming scheduled giveaways to cancel.', ephemeral: true });
          return;
        }
        if (!isAdminOrCreator(interaction, row)) {
          interaction.reply({ content: 'You are not authorized to cancel this giveaway.', ephemeral: true });
          return;
        }
        await db.run(`UPDATE giveaways SET status = 'canceled' WHERE id = ?`, row.id);
        await logAction(db, row.id, 'canceled', interaction.user.id);
        interaction.reply({ content: `Canceled upcoming giveaway ${row.id} scheduled for ${row.start_date}`, ephemeral: false });
        scheduler.checkDueGiveaways();
      }
    } catch (err) {
      console.error('Error canceling giveaway', err);
      interaction.reply({ content: 'Failed to cancel giveaway', ephemeral: true });
    }
    return;
  }

  if (name === 'giveaway_update') {
    if (!interaction.memberPermissions?.has('ManageGuild')) {
      interaction.reply({ content: 'You do not have permission to update giveaways.', ephemeral: true });
      return;
    }

    const id = interaction.options.getInteger('id');
    const startIso = interaction.options.getString('start_iso');
    const endIso = interaction.options.getString('end_iso');

    try {
      const row = await db.get(`SELECT * FROM giveaways WHERE id = ?`, id);
      if (!row) {
        interaction.reply({ content: `Giveaway ${id} not found`, ephemeral: true });
        return;
      }
      if (!isAdminOrCreator(interaction, row)) {
        interaction.reply({ content: 'You are not authorized to update this giveaway.', ephemeral: true });
        return;
      }

      if (startIso) {
        await db.run(`UPDATE giveaways SET start_iso = ? WHERE id = ?`, startIso, id);
        await logAction(db, id, `updated_start:${startIso}`, interaction.user.id);
      }
      if (endIso) {
        await db.run(`UPDATE giveaways SET end_iso = ? WHERE id = ?`, endIso, id);
        await logAction(db, id, `updated_end:${endIso}`, interaction.user.id);
      }

      interaction.reply({ content: `Updated giveaway ${id} times.`, ephemeral: false });
      scheduler.checkDueGiveaways();
    } catch (err) {
      console.error('Error updating giveaway', err);
      interaction.reply({ content: 'Failed to update giveaway', ephemeral: true });
    }
    return;
  }

  if (name === 'giveaway_control') {
    if (!interaction.memberPermissions?.has('ManageGuild')) {
      interaction.reply({ content: 'You do not have permission to control giveaways.', ephemeral: true });
      return;
    }

    const id = interaction.options.getInteger('id');
    const action = interaction.options.getString('action');

    try {
      const row = await db.get(`SELECT * FROM giveaways WHERE id = ?`, id);
      if (!row) {
        interaction.reply({ content: `Giveaway ${id} not found`, ephemeral: true });
        return;
      }
      if (!isAdminOrCreator(interaction, row)) {
        interaction.reply({ content: 'You are not authorized to control this giveaway.', ephemeral: true });
        return;
      }

      if (action === 'startnow') {
        if (row.status === 'active') {
          interaction.reply({ content: `Giveaway ${id} is already active.`, ephemeral: true });
          return;
        }
        await db.run(`UPDATE giveaways SET status = 'active' WHERE id = ?`, id);
        await logAction(db, id, 'startnow', interaction.user.id);
        const channel = await interaction.guild.channels.fetch(row.channel_id).catch(() => null);
        if (channel) {
          await channel.send(`Giveaway ${id} is starting now for prize: ${row.prize}`).catch(() => null);
        }
        interaction.reply({ content: `Started giveaway ${id} now.`, ephemeral: false });
      }

      else if (action === 'endnow') {
        if (row.status !== 'active' && row.status !== 'scheduled') {
          interaction.reply({ content: `Giveaway ${id} is not active or scheduled.`, ephemeral: true });
          return;
        }

        const startIso = row.start_iso || (row.start_date ? `${row.start_date}T00:00` : null);
        const endIso = row.end_iso || (row.end_date ? `${row.end_date}T23:59` : null);

        await db.run(`UPDATE giveaways SET status = 'ended' WHERE id = ?`, id);
        await logAction(db, id, 'endnow', interaction.user.id);

        if (startIso && endIso) {
          const winners = await computeWinners(db, startIso, endIso, 3);
          const winnersText = winners.map((id, i) => `• <@${id}> — Prize ${i + 1}`).join('\n') || 'No eligible winners.';
          const channel = await interaction.guild.channels.fetch(row.channel_id).catch(() => null);
          if (channel) {
            await channel.send(`Giveaway ${row.id} ended. Winners:\n${winnersText}`).catch(() => null);
          }
          interaction.reply({ content: `Ended giveaway ${id} and posted winners.`, ephemeral: false });
        } else {
          interaction.reply({ content: `Giveaway ${id} ended but start/end window is not set, so no winners were computed.`, ephemeral: false });
        }
      }

      else {
        interaction.reply({ content: 'Unknown action. Use startnow or endnow.', ephemeral: true });
      }
    } catch (err) {
      console.error('Error controlling giveaway', err);
      interaction.reply({ content: 'Failed to control giveaway', ephemeral: true });
    }
    return;
  }

  if (name === 'giveaway_run_draw') {
    if (!interaction.memberPermissions?.has('ManageGuild')) {
      interaction.reply({ content: 'You do not have permission to run draws.', ephemeral: true });
      return;
    }

    const id = interaction.options.getInteger('id');
    try {
      await runWeeklyDraw(db, client, interaction, id);
    } catch (err) {
      console.error('Error running manual draw', err);
      interaction.reply({ content: 'Failed to run manual draw', ephemeral: true });
    }
    return;
  }
}

// Manual draw implementation. If giveawayId is given, draw for that giveaway; otherwise run Thu->Wed weekly draw.
async function runWeeklyDraw(db, client, interaction, giveawayId = null) {
  if (giveawayId) {
    const row = await db.get(`SELECT * FROM giveaways WHERE id = ?`, giveawayId);
    if (!row) {
      await interaction.reply({ content: `Giveaway ${giveawayId} not found`, ephemeral: true });
      return;
    }
    if (!isAdminOrCreator(interaction, row)) {
      await interaction.reply({ content: 'You are not authorized to run the draw for this giveaway.', ephemeral: true });
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

  // Standard weekly draw Thu->Wed
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
    await channel.send(`(Manual) Weekly Final Draw — Winners\nThis draw covers check‑ins from Thursday ${startDate} through Wednesday ${endDate}.\n${winnersText}`).catch(() => null);
  }
  await logAction(db, null, 'manual_weekly_draw', interaction.user.id);
  await interaction.reply({ content: 'Manual weekly draw complete.', ephemeral: true });
}

module.exports = { ensureCommandsRegistered, handleInteraction, runWeeklyDraw };
