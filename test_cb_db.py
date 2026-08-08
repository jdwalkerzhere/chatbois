import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cb_db


class DatabaseTest(unittest.TestCase):
    def test_round_trip_and_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "chatbois.db"
            with patch.object(cb_db, "DB_FILE", database):
                self.assertEqual(cb_db.load("missing", {}), {})
                cb_db.save("users", {"boi": {"chats": ["general"]}})
                self.assertEqual(
                    cb_db.load("users", {}),
                    {"boi": {"chats": ["general"]}},
                )
                cb_db.save("users", {"boi": {"chats": []}})
                self.assertEqual(
                    cb_db.load("users", {}), {"boi": {"chats": []}}
                )


if __name__ == "__main__":
    unittest.main()

