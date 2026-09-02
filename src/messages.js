// src/messages.js
// Centralized user-facing message templates for daily check-ins and weekly draw.

const dailyCheckinMessage = (date) =>
  `Daily Check‑in — ${date}\nReact with ✅ to mark today's check‑in. This is reaction‑only — please don't send messages in this channel for check‑ins. Remove your ✅ if you need to undo your check‑in.`;

const reactionTooltip = `React with ✅ — reactions only. Removing the ✅ undoes your check‑in.`;

const weeklyDrawAnnouncement = (startDate, endDate, winnersText) =>
  `Weekly Final Draw — Winners\nThis draw covers check‑ins from Thursday ${startDate} through Wednesday ${endDate} (Thursday = Day 1).\nCongratulations to this week's winners:\n${winnersText}\nThanks to everyone who checked in this week!`;

module.exports = {
  dailyCheckinMessage,
  reactionTooltip,
  weeklyDrawAnnouncement,
};
