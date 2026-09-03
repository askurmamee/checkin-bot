const { Client, GatewayIntentBits } = require('discord.js');

const TOKEN = process.env.DISCORD_TOKEN;
const CHANNEL_ARG = process.argv[2]; // optional: node test_reaction_post.js <channelId>
const CHECKIN_CHANNEL_ID = CHANNEL_ARG || process.env.CHECKIN_CHANNEL_ID || process.env.INPUT_CHANNEL_ID;

if (!TOKEN) {
  console.error('Missing DISCORD_TOKEN env');
  process.exit(1);
}
if (!CHECKIN_CHANNEL_ID) {
  console.error('Missing CHECKIN_CHANNEL_ID env, CLI arg, or workflow input');
  process.exit(1);
}

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

const MESSAGE_CONTENT = `Daily Check-in! React with ✅ to enter today's check-in.`;

client.once('ready', async () => {
  try {
    const ch = await client.channels.fetch(CHECKIN_CHANNEL_ID);
    if (!ch || !ch.send) {
      console.error('Channel not found or not a text channel:', CHECKIN_CHANNEL_ID);
      process.exit(1);
    }

    const msg = await ch.send(MESSAGE_CONTENT);
    await msg.react('✅');
    console.log('Posted message:', msg.id, 'in channel', CHECKIN_CHANNEL_ID);
  } catch (err) {
    console.error('Failed to post reaction message', err);
  } finally {
    client.destroy();
    process.exit(0);
  }
});

client.login(TOKEN);
