"""Check that normal application startup preserves saved accounts and bookings."""

import sqlite3
import shutil
import subprocess
import sys
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
                main.buy_tickets(connection, user.id, run.run.id, 2, ""),
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
            tickets = main.list_user_tickets(connection, user.id)
            self.assertEqual(len(tickets), 1)
            self.assertEqual(tickets[0].ticket.number, 2)
        finally:
            connection.close()

    def test_legacy_date_column_migrates_without_losing_tickets(self) -> None:
        """Upgrade the old date spelling while preserving ids and foreign keys."""
        create_database(self.db_path)
        connection = main.open_connection(self.db_path)
        try:
            before = [tuple(row) for row in connection.execute("SELECT * FROM ticket")]
            connection.execute("ALTER TABLE run RENAME COLUMN date TO run_date")
            connection.commit()
        finally:
            connection.close()
        ensure_database_exists(self.db_path)
        connection = main.open_connection(self.db_path)
        try:
            self.assertIn("date", [row[1] for row in connection.execute("PRAGMA table_info(run)")])
            self.assertEqual(before, [tuple(row) for row in connection.execute("SELECT * FROM ticket")])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertIsNotNone(main.authenticate_user(connection, "Bob", "pqr123#!"))
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

    def test_real_process_restart_preserves_account_service_and_booking(self) -> None:
        """Run main.py twice, from another cwd, and verify the same saved records."""
        project = Path(self.directory.name) / "project"
        project.mkdir()
        source = Path(__file__).resolve().parent
        for name in ("main.py", "create_database.py", "user.py", "service.py", "run.py",
                     "bus.py", "bus_model.py", "ticket.py"):
            shutil.copy2(source / name, project / name)

        def launch(inputs: list[str]) -> str:
            """Execute the unmodified application in a separate Python process."""
            result = subprocess.run(
                [sys.executable, str(project / "main.py")],
                cwd=self.directory.name,
                input="\n".join(inputs) + "\n",
                capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

        first = launch([
            "1", "Bob", "pqr123#!", "2", "A persistent route, 9am", "3",
            "2", "RestartCustomer", "password", "1", "RestartCustomer", "password",
            "2", "1", "2", "", "4", "3",
        ])
        self.assertIn("Booking confirmed!", first)
        second = launch(["1", "RestartCustomer", "password", "3", "4", "3"])
        self.assertIn("Welcome back, RestartCustomer!", second)
        self.assertIn("2 seat(s)", second)
        self.assertIn("A persistent route, 9am", second)
        connection = main.open_connection(project / "flyonwheels.db")
        try:
            user = main.authenticate_user(connection, "RestartCustomer", "password")
            self.assertFalse(user.admin)
            ticket, = main.list_user_tickets(connection, user.id)
            self.assertEqual(ticket.ticket.number, 2)
            self.assertEqual(ticket.service.name, "A persistent route, 9am")
        finally:
            connection.close()
        self.assertFalse(self.db_path.exists(), "Launching from another cwd must not create a second DB")


if __name__ == "__main__":
    unittest.main()
