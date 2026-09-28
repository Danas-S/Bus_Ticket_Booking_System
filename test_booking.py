"""Focused account, service and booking rules using isolated SQLite databases."""

import io
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import main
from bus import Bus
from bus_model import BusModel
from create_database import RUN_DAYS, create_database, hash_password
from run import Run
from service import Service
from test_database import get_table_names
from ticket import Ticket
from user import User


class TestBookingRules(unittest.TestCase):
    """Verify user-visible rules and the data saved by successful operations."""

    def setUp(self) -> None:
        """Seed a private database and create an ordinary customer."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "flyonwheels.db"
        create_database(self.db_path)
        self.connection = main.open_connection(self.db_path)
        self.addCleanup(self.connection.close)
        self.assertTrue(main.create_account(self.connection, "Customer", "password"))
        self.user = main.authenticate_user(self.connection, "Customer", "password")
        self.run = main.list_future_runs(self.connection)[0]

    def test_seed_schema_and_relationships(self) -> None:
        """Check the six canonical tables, required starter data and foreign keys."""
        self.assertEqual(
            get_table_names(self.connection),
            ["bus", "bus_model", "run", "service", "ticket", "user"],
        )
        self.assertEqual(
            [service.name for service in main.list_services(self.connection)],
            ["Dublin to Kilkenny, 7pm", "Dublin to Letterkenny, 8am", "Dublin to Wicklow, 6pm"],
        )
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM run").fetchone()[0], 21)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM bus").fetchone()[0], 6)
        bob = main.authenticate_user(self.connection, "Bob", "pqr123#!")
        self.assertTrue(bob.admin)
        self.assertEqual(bob.password, hash_password("pqr123#!"))
        booking, = main.list_user_tickets(self.connection, bob.id)
        self.assertEqual(booking.ticket.number, 1)
        self.assertEqual(booking.service.name, "Dublin to Letterkenny, 8am")
        self.assertEqual(booking.run.date, (date.today() + timedelta(days=1)).isoformat())
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO ticket (user_id, run_id, number) VALUES (?, ?, ?)",
                (-1, self.run.run.id, 1),
            )
        self.connection.rollback()

    def test_account_validation_and_authentication(self) -> None:
        """Reject blanks/duplicates and authenticate a trimmed non-admin account."""
        for username, password in [("", "pwd"), ("  ", "pwd"), ("New", ""), ("New", "  "),
                                   ("Customer", "different"), (" Customer ", "different")]:
            with self.subTest(username=username, password=password):
                self.assertFalse(main.create_account(self.connection, username, password))
                self.assertFalse(self.connection.in_transaction)
        self.assertTrue(main.create_account(self.connection, " NewUser ", " spaced password "))
        user = main.authenticate_user(self.connection, "NewUser", " spaced password ")
        self.assertIsInstance(user, User)
        self.assertFalse(user.admin)
        self.assertNotEqual(user.password, " spaced password ")
        self.assertIsNone(main.authenticate_user(self.connection, "NewUser", "wrong"))
        self.assertIsNone(main.authenticate_user(self.connection, "Nobody", "password"))
        self.assertIsNone(main.authenticate_user(self.connection, "' OR 1=1 --", "password"))

    def test_service_creation_has_seven_runs_and_two_buses(self) -> None:
        """A new service is immediately scheduled on all seven dates with A/B buses."""
        self.assertTrue(main.create_service(self.connection, " New route, 9am "))
        service = main.list_services(self.connection)[-1]
        self.assertIsInstance(service, Service)
        self.assertEqual(service.name, "New route, 9am")
        dates = [row[0] for row in self.connection.execute(
            "SELECT date FROM run WHERE service_id = ? ORDER BY date", (service.id,)
        )]
        self.assertEqual(dates, [
            (date.today() + timedelta(days=offset)).isoformat() for offset in range(RUN_DAYS)
        ])
        buses = [tuple(row) for row in self.connection.execute(
            "SELECT bm.name, b.schedule_type FROM bus b "
            "JOIN bus_model bm ON bm.id = b.bus_model_id "
            "WHERE b.service_id = ? ORDER BY bm.name", (service.id,)
        )]
        self.assertEqual(buses, [("A", "weekend"), ("B", "workday")])

    def test_service_rejections_leave_no_partial_schedule(self) -> None:
        """Blank, duplicate and missing-model failures leave no extra service/run rows."""
        for name in ("", "   ", "Dublin to Kilkenny, 7pm"):
            with self.subTest(name=name):
                self.assertFalse(main.create_service(self.connection, name))
        with self.connection:
            self.connection.execute("DELETE FROM bus WHERE bus_model_id IN "
                                    "(SELECT id FROM bus_model WHERE name = 'A')")
            self.connection.execute("DELETE FROM bus_model WHERE name = 'A'")
        self.assertFalse(main.create_service(self.connection, "Incomplete route"))
        self.assertEqual(len(main.list_services(self.connection)), 3)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM run").fetchone()[0], 21)
        self.assertFalse(self.connection.in_transaction)

    def test_booking_updates_availability_and_uses_models(self) -> None:
        """A two-seat purchase decreases availability and creates a linked Ticket."""
        self.assertIsInstance(self.run.run, Run)
        self.assertIsInstance(self.run.service, Service)
        self.assertIsInstance(self.run.bus, Bus)
        self.assertIsInstance(self.run.bus_model, BusModel)
        self.assertEqual(main.buy_tickets(
            self.connection, self.user.id, self.run.run.id, 2, ""
        ), "Booking confirmed!")
        refreshed = next(item for item in main.list_future_runs(self.connection)
                         if item.run.id == self.run.run.id)
        self.assertEqual(refreshed.available_seats, self.run.available_seats - 2)
        booking, = main.list_user_tickets(self.connection, self.user.id)
        self.assertIsInstance(booking.ticket, Ticket)
        self.assertEqual(booking.ticket.number, 2)
        self.assertEqual(booking.ticket.user_id, self.user.id)
        self.assertEqual(booking.ticket.run_id, self.run.run.id)

    def test_booking_rejects_bad_quantities_and_run_ids(self) -> None:
        """Zero, negative, fractional, excessive and invalid-run requests write nothing."""
        for quantity in (0, -2, 1.5):
            with self.subTest(quantity=quantity):
                self.assertEqual(main.buy_tickets(
                    self.connection, self.user.id, self.run.run.id, quantity, ""
                ), "Invalid number of tickets.")
        self.assertEqual(main.buy_tickets(
            self.connection, self.user.id, self.run.run.id, self.run.available_seats + 1, ""
        ), "Not enough seats available.")
        self.assertEqual(main.buy_tickets(
            self.connection, self.user.id, -1, 1, ""
        ), "Invalid run selection.")
        self.assertEqual(main.list_user_tickets(self.connection, self.user.id), [])
        self.assertFalse(self.connection.in_transaction)

    def test_cancellation_and_invalid_confirmation_write_nothing(self) -> None:
        """Escape cancels without writing, and arbitrary text cannot confirm a purchase."""
        for confirmation in ("esc", " ESC ", "yes"):
            with self.subTest(confirmation=confirmation):
                result = main.buy_tickets(
                    self.connection, self.user.id, self.run.run.id, 1, confirmation
                )
                self.assertNotEqual(result, "Booking confirmed!")
        self.assertEqual(main.list_user_tickets(self.connection, self.user.id), [])

    def test_weekday_weekend_capacities_and_seed_booking(self) -> None:
        """Every run uses its date's bus capacity minus actual booked quantities."""
        seen = set()
        for details in main.list_future_runs(self.connection):
            weekend = date.fromisoformat(details.run.date).weekday() >= 5
            seen.add(weekend)
            self.assertEqual(details.bus_model.name, "A" if weekend else "B")
            self.assertEqual(details.bus_model.seats, 30 if weekend else 50)
            self.assertEqual(details.bus.schedule_type, "weekend" if weekend else "workday")
            sold = self.connection.execute(
                "SELECT COALESCE(SUM(number), 0) FROM ticket WHERE run_id = ?",
                (details.run.id,),
            ).fetchone()[0]
            self.assertEqual(details.available_seats, details.bus_model.seats - sold)
        self.assertEqual(seen, {False, True})

    def test_menu_selection_matches_displayed_position(self) -> None:
        """A newly sorted first route is displayed as choice 1 and receives the booking."""
        self.assertTrue(main.create_service(self.connection, "A route, 9am"))
        first = main.list_future_runs(self.connection)[0]
        self.assertNotEqual(first.run.id, 1)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["2", "1", "2", "", "3", "4"]), redirect_stdout(output):
            main.customer_menu(self.connection, self.user)
        self.assertIn(f"Run 1: {first.run.date} | A route, 9am", output.getvalue())
        self.assertIn("2 seat(s)", output.getvalue())
        booking, = main.list_user_tickets(self.connection, self.user.id)
        self.assertEqual(booking.ticket.run_id, first.run.id)

    def test_menu_rejects_invalid_numeric_inputs(self) -> None:
        """Non-numeric, out-of-range and nonpositive choices return safely to the menu."""
        cases = [("abc", "1", "Invalid numeric input."),
                 ("1", "abc", "Invalid numeric input."),
                 ("0", "1", "Invalid run selection."),
                 ("999", "1", "Invalid run selection."),
                 ("1", "0", "Invalid number of tickets."),
                 ("1", "-1", "Invalid number of tickets."),
                 ("1", "100", "Not enough seats available.")]
        for run_choice, quantity, message in cases:
            with self.subTest(run_choice=run_choice, quantity=quantity):
                output = io.StringIO()
                with patch("builtins.input", side_effect=["2", run_choice, quantity, "4"]), redirect_stdout(output):
                    main.customer_menu(self.connection, self.user)
                self.assertIn(message, output.getvalue())
        self.assertEqual(main.list_user_tickets(self.connection, self.user.id), [])

    def test_past_run_cannot_be_booked_but_history_remains(self) -> None:
        """A dated run disappears from sale after its day but keeps purchased tickets."""
        self.assertEqual(main.buy_tickets(
            self.connection, self.user.id, self.run.run.id, 1, ""
        ), "Booking confirmed!")
        with self.connection:
            self.connection.execute("UPDATE run SET date = ? WHERE id = ?", (
                (date.today() - timedelta(days=1)).isoformat(), self.run.run.id
            ))
        self.assertEqual(main.buy_tickets(
            self.connection, self.user.id, self.run.run.id, 1, ""
        ), "Invalid run selection.")
        self.assertEqual(len(main.list_user_tickets(self.connection, self.user.id)), 1)

    def test_two_connections_cannot_oversell_last_seat(self) -> None:
        """Two simultaneous buyers competing for one remaining seat yield one booking."""
        self.assertEqual(main.buy_tickets(
            self.connection, self.user.id, self.run.run.id, self.run.available_seats - 1, ""
        ), "Booking confirmed!")
        start = Barrier(2)

        def buy_last_seat() -> str:
            """Wait for the other buyer, then purchase through a separate connection."""
            connection = main.open_connection(self.db_path)
            try:
                start.wait(timeout=5)
                return main.buy_tickets(connection, self.user.id, self.run.run.id, 1, "")
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(buy_last_seat) for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual(results, ["Booking confirmed!", "Not enough seats available."])
        remaining = next(item.available_seats for item in main.list_future_runs(self.connection)
                         if item.run.id == self.run.run.id)
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
