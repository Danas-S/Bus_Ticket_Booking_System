"""Create and seed the FlyOnWheels SQLite database."""

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path


DB_PATH = Path(__file__).resolve().with_name("flyonwheels.db")


def ensure_database_exists(db_path: str | Path = DB_PATH) -> None:
    """Initialize a missing/empty database, or validate it without resetting data.

    Raise ValueError for an incompatible existing schema so user data is never
    silently replaced. Resetting remains an explicit create_database() action.
    """
    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables:
            expected_columns = {
                "user": {"id", "username", "password", "admin"},
                "service": {"id", "name"},
                "bus_model": {"id", "name", "seats"},
                "run": {"id", "service_id", "run_date"},
                "bus": {"id", "service_id", "bus_model_id", "schedule_type"},
                "ticket": {"id", "user_id", "run_id", "number"},
            }
            for table, required in expected_columns.items():
                columns = {
                    row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                if not required <= columns:
                    raise ValueError(
                        f"Incompatible database: check the {table} table. "
                        "Back up your data before explicitly resetting it."
                    )
            return
    finally:
        connection.close()
    create_database(db_path)

# NOTE: This file contains both Part 1 (plural-table) and Part 2 (singular-table)
# database setup paths so each assignment requirement remains demonstrable.


# hash plain-text passwords before storing in the users table

def hash_password(plain_text_password: str) -> str:
    """Return a SHA-256 hash for the supplied password."""
    return hashlib.sha256(plain_text_password.encode("utf-8")).hexdigest()


# create all database tables that map to the bus booking class diagram
def create_tables(connection: sqlite3.Connection) -> None:
    """Create all required tables if they do not already exist."""
    cursor = connection.cursor()

    # These tables match the class diagram concepts 1:1.

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            admin INTEGER NOT NULL CHECK (admin IN (0, 1))
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bus_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            seats INTEGER NOT NULL CHECK (seats > 0)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            run_date TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            bus_model_id INTEGER NOT NULL,
            schedule_type TEXT NOT NULL CHECK (schedule_type IN ('weekend', 'workday')),
            FOREIGN KEY (service_id) REFERENCES services (id),
            FOREIGN KEY (bus_model_id) REFERENCES bus_models (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            run_id INTEGER NOT NULL,
            seat_number INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (run_id) REFERENCES runs (id)
        )
        """
    )

    connection.commit()


# insert the fixed starter rows for user service and bus model tables
def seed_reference_data(connection: sqlite3.Connection) -> None:
    """Insert required fixed records for users, services, and bus models."""
    cursor = connection.cursor()

    # Delete child rows first so foreign-key constraints are respected.
    cursor.execute("DELETE FROM tickets")
    cursor.execute("DELETE FROM buses")
    cursor.execute("DELETE FROM runs")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM services")
    cursor.execute("DELETE FROM bus_models")

    cursor.execute(
        """
        INSERT INTO users (username, password, admin)
        VALUES (?, ?, ?)
        """,
        ("Bob", hash_password("pqr123#!"), 1),
    )

    service_names = [
        "Dublin to Kilkenny, 7pm",
        "Dublin to Letterkenny, 8am",
        "Dublin to Wicklow, 6pm",
    ]
    cursor.executemany(
        "INSERT INTO services (name) VALUES (?)",
        [(name,) for name in service_names],
    )

    bus_models = [("A", 30), ("B", 50)]
    cursor.executemany(
        "INSERT INTO bus_models (name, seats) VALUES (?, ?)",
        bus_models,
    )

    connection.commit()


# create run rows for each service for seven days starting from today
def seed_runs(connection: sqlite3.Connection) -> None:
    """Insert runs for 7 days from today for each available service."""
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM services ORDER BY id")
    service_ids = [row[0] for row in cursor.fetchall()]

    rows_to_insert = []
    start = date.today()
    # Create one run per service for each day in the 7-day window.
    for day_offset in range(7):
        run_day = (start + timedelta(days=day_offset)).isoformat()
        for service_id in service_ids:
            rows_to_insert.append((service_id, run_day))

    cursor.executemany(
        "INSERT INTO runs (service_id, run_date) VALUES (?, ?)",
        rows_to_insert,
    )

    connection.commit()


# assign two physical buses to each service with weekend and workday schedules
def seed_buses(connection: sqlite3.Connection) -> None:
    """Insert two buses per service using model A for weekends and B for workdays."""
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM services ORDER BY id")
    service_ids = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT id, name FROM bus_models")
    model_map = {name: model_id for model_id, name in cursor.fetchall()}

    bus_rows = []
    for service_id in service_ids:
        bus_rows.append((service_id, model_map["A"], "weekend"))
        bus_rows.append((service_id, model_map["B"], "workday"))

    cursor.executemany(
        "INSERT INTO buses (service_id, bus_model_id, schedule_type) VALUES (?, ?, ?)",
        bus_rows,
    )

    connection.commit()


# create the required single ticket for Bob on tomorrow's Letterkenny run
def seed_ticket(connection: sqlite3.Connection) -> None:
    """Insert one ticket owned by Bob for tomorrow's Dublin to Letterkenny run."""
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", ("Bob",))
    user_row = cursor.fetchone()
    if user_row is None:
        raise ValueError("Required user 'Bob' not found.")
    user_id = user_row[0]

    cursor.execute(
        "SELECT id FROM services WHERE name = ?",
        ("Dublin to Letterkenny, 8am",),
    )
    service_row = cursor.fetchone()
    if service_row is None:
        raise ValueError("Required service 'Dublin to Letterkenny, 8am' not found.")
    service_id = service_row[0]

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    # Pick the specific next-day run for the Dublin to Letterkenny service.
    cursor.execute(
        "SELECT id FROM runs WHERE service_id = ? AND run_date = ? ORDER BY id LIMIT 1",
        (service_id, tomorrow),
    )
    run_row = cursor.fetchone()
    if run_row is None:
        raise ValueError("Required run for Dublin to Letterkenny on the next day not found.")
    run_id = run_row[0]

    cursor.execute(
        "INSERT INTO tickets (user_id, run_id, seat_number) VALUES (?, ?, ?)",
        (user_id, run_id, 1),
    )

    connection.commit()


# orchestrate table creation and all seeding steps into one setup workflow
def create_and_seed_database(db_path: str = DB_PATH) -> None:
    """Create flyonwheels.db and populate all required assignment data."""
    connection = sqlite3.connect(db_path)
    try:
        # Explicitly enable FK checks for this SQLite connection.
        # NOTE: FK checks prove relationships in the diagram are enforced in DB.
        connection.execute("PRAGMA foreign_keys = ON")
        create_tables(connection)
        seed_reference_data(connection)
        seed_runs(connection)
        seed_buses(connection)
        seed_ticket(connection)
    finally:
        connection.close()


# provide the test-facing database setup function used by main and tests
def create_database(db_path: str = DB_PATH) -> None:
    """Create and seed the transport booking database file."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()

        # Rebuild the singular table schema expected by Part 2 tests.
        cursor.executescript(
            """
            DROP TABLE IF EXISTS ticket;
            DROP TABLE IF EXISTS bus;
            DROP TABLE IF EXISTS run;
            DROP TABLE IF EXISTS bus_model;
            DROP TABLE IF EXISTS service;
            DROP TABLE IF EXISTS user;

            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                admin INTEGER NOT NULL CHECK (admin IN (0, 1))
            );

            CREATE TABLE service (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE bus_model (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                seats INTEGER NOT NULL CHECK (seats > 0)
            );

            CREATE TABLE run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                run_date TEXT NOT NULL,
                FOREIGN KEY (service_id) REFERENCES service (id)
            );

            CREATE TABLE bus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                bus_model_id INTEGER NOT NULL,
                schedule_type TEXT NOT NULL CHECK (schedule_type IN ('weekend', 'workday')),
                FOREIGN KEY (service_id) REFERENCES service (id),
                FOREIGN KEY (bus_model_id) REFERENCES bus_model (id)
            );

            CREATE TABLE ticket (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                number INTEGER NOT NULL CHECK (number > 0),
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (run_id) REFERENCES run (id)
            );
            """
        )

        cursor.execute(
            "INSERT INTO user (username, password, admin) VALUES (?, ?, ?)",
            ("Bob", hash_password("pqr123#!"), 1),
        )

        # NOTE: Service names exactly match assignment wording.

        services = [
            "Dublin to Kilkenny, 7pm",
            "Dublin to Letterkenny, 8am",
            "Dublin to Wicklow, 6pm",
        ]
        cursor.executemany("INSERT INTO service (name) VALUES (?)", [(name,) for name in services])
        cursor.executemany("INSERT INTO bus_model (name, seats) VALUES (?, ?)", [("A", 30), ("B", 50)])

        service_ids = [row[0] for row in cursor.execute("SELECT id FROM service ORDER BY id").fetchall()]
        start = date.today()
        run_rows = []
        # NOTE: Generate 7 daily runs per service starting from today.
        for day_offset in range(7):
            run_day = (start + timedelta(days=day_offset)).isoformat()
            for service_id in service_ids:
                run_rows.append((service_id, run_day))
        cursor.executemany("INSERT INTO run (service_id, run_date) VALUES (?, ?)", run_rows)

        model_rows = cursor.execute("SELECT id, name FROM bus_model").fetchall()
        model_map = {row[1]: row[0] for row in model_rows}
        bus_rows = []
        # NOTE: Weekend uses model A; workday uses model B.
        for service_id in service_ids:
            bus_rows.append((service_id, model_map["A"], "weekend"))
            bus_rows.append((service_id, model_map["B"], "workday"))
        cursor.executemany(
            "INSERT INTO bus (service_id, bus_model_id, schedule_type) VALUES (?, ?, ?)",
            bus_rows,
        )

        bob_id = cursor.execute("SELECT id FROM user WHERE username = 'Bob'").fetchone()[0]
        letterkenny_id = cursor.execute(
            "SELECT id FROM service WHERE name = ?",
            ("Dublin to Letterkenny, 8am",),
        ).fetchone()[0]
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        run_id = cursor.execute(
            "SELECT id FROM run WHERE service_id = ? AND run_date = ? ORDER BY id LIMIT 1",
            (letterkenny_id, tomorrow),
        ).fetchone()[0]
        # NOTE: Initial ticket proves ticket->run->service relationship in seed data.
        cursor.execute("INSERT INTO ticket (user_id, run_id, number) VALUES (?, ?, ?)", (bob_id, run_id, 1))

        connection.commit()
    finally:
        connection.close()


# provide a simple script entry point for creating and seeding the database
def main() -> None:
    """Run database creation and print a short confirmation message."""
    # NOTE: Run this script first before running test_database.py.
    create_and_seed_database()
    print("Created and seeded flyonwheels.db")


if __name__ == "__main__":
    main()
