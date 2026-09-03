const { Client, GatewayIntentBits } = require('discord.js');

const commands = [
  {
    name: 'giveaway_start',
    description: 'Schedule a giveaway start date (YYYY-MM-DD)',
    options: [
      { name: 'date', type: 3, description: 'Start date (YYYY-MM-DD)', required: true },
      { name: 'end_date', type: 3, description: 'Optional end date (YYYY-MM-DD)', required: false },
      { name: 'prize', type: 3, description: 'Prize description', required: false },
    ],
  },
  { name: 'giveaway_cancel', description: 'Cancel a scheduled giveaway', options: [{ name: 'id', type: 4, description: 'Giveaway id', required: false }] },
  {
    name: 'giveaway_update',
    description: 'Update giveaway times (id required)',
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
  { name: 'giveaway_run_draw', description: 'Run a giveaway draw immediately (admin)', options: [{ name: 'id', type: 4, description: 'Giveaway id (optional)', required: false }] },
];

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.once('ready', async () => {
  try {
    for (const guild of client.guilds.cache.values()) {
      await guild.commands.set(commands);
      console.log(`Registered commands for guild ${guild.id}`);
    }
  } catch (err) {
    console.error('Failed to register commands', err);
  } finally {
    client.destroy();
    process.exit(0);
  }
});

client.login(process.env.DISCORD_TOKEN);
