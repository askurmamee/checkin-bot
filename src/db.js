// src/db.js
// Simple SQLite wrapper and migrations for checkin bot.
const sqlite3 = require('sqlite3').verbose();
const { open } = require('sqlite');

async function init(dbPath) {
  const db = await open({ filename: dbPath || process.env.DB_PATH || './checkins.db', driver: sqlite3.Database });

  // Create tables if they don't exist
  await db.exec(`
    CREATE TABLE IF NOT EXISTS daily_messages (
      date TEXT PRIMARY KEY,
      channel_id TEXT,
      message_id TEXT
    );
  `);

  await db.exec(`
    CREATE TABLE IF NOT EXISTS checkins (
      user_id TEXT,
      date TEXT,
      PRIMARY KEY(user_id, date)
    );
  `);

  await db.exec(`
    CREATE TABLE IF NOT EXISTS giveaways (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      start_date TEXT,
      end_date TEXT,
      prize TEXT,
      channel_id TEXT,
      status TEXT DEFAULT 'scheduled',
      created_at TEXT DEFAULT (datetime('now'))
    );
  `);

  await db.exec(`
    CREATE TABLE IF NOT EXISTS action_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      giveaway_id INTEGER,
      action TEXT,
      user_id TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
  `);

  // Ensure optional columns (for times / creator) exist — add them if missing
  const cols = await db.all(`PRAGMA table_info('giveaways')`);
  const colNames = cols.map(c => c.name);
  if (!colNames.includes('start_iso')) {
    await db.exec(`ALTER TABLE giveaways ADD COLUMN start_iso TEXT`);
  }
  if (!colNames.includes('end_iso')) {
    await db.exec(`ALTER TABLE giveaways ADD COLUMN end_iso TEXT`);
  }
  if (!colNames.includes('creator_id')) {
    await db.exec(`ALTER TABLE giveaways ADD COLUMN creator_id TEXT`);
  }

  return db;
}

module.exports = { init };
