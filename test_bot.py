import os
import sqlite3
import tempfile
import unittest

import bot


class BotTests(unittest.TestCase):
    def test_get_start_date_returns_none_for_invalid_stored_date(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        bot.DB_PATH = path
        bot.init_db()

        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('start_date', ?)",
            ("not-a-date",),
        )
        conn.commit()
        conn.close()

        self.assertIsNone(bot.get_start_date())


if __name__ == "__main__":
    unittest.main()
