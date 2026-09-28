"""Check that normal application startup preserves saved accounts and bookings."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from create_database import create_database, ensure_database_exists


class TestPersistence(unittest.TestCase):
    """Exercise real SQLite files without changing the working database."""

    def setUp(self) -> None:
        """Allocate a temporary database for each test."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "flyonwheels.db"

    def test_account_and_booking_survive_startup(self) -> None:
        """Re-enter main after closing a connection and verify saved records."""
        create_database(self.db_path)
        connection = main.open_connection(self.db_path)
        try:
            self.assertTrue(main.create_account(connection, "RestartCustomer", "test-password"))
            user = main.authenticate_user(connection, "RestartCustomer", "test-password")
            run = main.list_future_runs(connection)[0]
            self.assertEqual(
                main.buy_tickets(connection, user["id"], run["run_id"], 2, ""),
                "Booking confirmed!",
            )
        finally:
            connection.close()

        with patch("builtins.input", return_value="3"), patch("builtins.print"):
            main.main(self.db_path)

        connection = main.open_connection(self.db_path)
        try:
            user = main.authenticate_user(connection, "RestartCustomer", "test-password")
            self.assertIsNotNone(user)
            tickets = main.list_user_tickets(connection, user["id"])
            self.assertEqual(len(tickets), 1)
            self.assertEqual(tickets[0]["number"], 2)
        finally:
            connection.close()

    def test_unknown_schema_is_preserved(self) -> None:
        """Refuse an incompatible database instead of destroying its contents."""
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("CREATE TABLE saved_data (value TEXT)")
            connection.execute("INSERT INTO saved_data VALUES ('keep me')")
            connection.commit()
            with self.assertRaises(ValueError):
                ensure_database_exists(self.db_path)
            self.assertEqual(
                connection.execute("SELECT value FROM saved_data").fetchone()[0], "keep me"
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
