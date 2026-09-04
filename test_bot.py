import os
import sqlite3
import tempfile
import unittest

import bot


class BotTests(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.path = path
        self.original_db_path = bot.DB_PATH
        bot.DB_PATH = path
        bot.init_db()

    def tearDown(self):
        bot.DB_PATH = self.original_db_path
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_get_start_date_returns_none_for_invalid_stored_date(self):
        conn = sqlite3.connect(self.path)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('start_date', ?)",
            ("not-a-date",),
        )
        conn.commit()
        conn.close()

        self.assertIsNone(bot.get_start_date())
        self.assertEqual(
            bot.get_start_date_error_message(),
            "Stored event start date is invalid. Reset it with /setstartdate YYYY-MM-DD.",
        )

    def test_get_total_checkins_for_day_scopes_to_active_event(self):
        bot.set_start_date("2099-01-01")
        conn = sqlite3.connect(self.path)
        conn.execute(
            "INSERT INTO checkins (user_id, event_day, event_start) VALUES (?, ?, ?)",
            (1, 1, "2099-01-01"),
        )
        conn.execute(
            "INSERT INTO checkins (user_id, event_day, event_start) VALUES (?, ?, ?)",
            (2, 1, "legacy"),
        )
        conn.commit()
        conn.close()

        self.assertEqual(bot.get_total_checkins_for_day(1), 1)

    def test_chunk_lines_splits_long_lines_and_keeps_first_prefix(self):
        chunks = bot.chunk_lines(["x" * 80], prefix="HEADER", max_length=40)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0].startswith("HEADER"))
        self.assertTrue(all(len(chunk) <= 40 for chunk in chunks))
        self.assertTrue(all(not chunk.startswith("HEADER") for chunk in chunks[1:]))

    def test_chunk_lines_handles_multiple_chunks(self):
        chunks = bot.chunk_lines(
            [f"line {index}" for index in range(20)],
            prefix="HEADER",
            max_length=50,
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 50 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
