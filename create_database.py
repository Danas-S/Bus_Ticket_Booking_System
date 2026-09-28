"""Create and seed the FlyOnWheels SQLite database."""

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path


DB_PATH = Path(__file__).resolve().with_name("flyonwheels.db")
RUN_DAYS = 7


def ensure_database_exists(db_path: str | Path = DB_PATH) -> None:
    """Initialize a missing/empty database, or validate it without resetting data.

    Raise ValueError for an incompatible existing schema so user data is never
    silently replaced. Resetting remains an explicit create_database() action.
    Older singular databases have run.run_date renamed to the required run.date.
    """
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
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
                "run": {"id", "service_id", "date"},
                "bus": {"id", "service_id", "bus_model_id", "schedule_type"},
                "ticket": {"id", "user_id", "run_id", "number"},
            }
            legacy_run_date = False
            for table, required in expected_columns.items():
                columns = {
                    row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                if table == "run" and "run_date" in columns and "date" not in columns:
                    legacy_run_date = True
                    columns.add("date")
                if not required <= columns:
                    raise ValueError(
                        f"Incompatible database: check the {table} table. "
                        "Back up your data before explicitly resetting it."
                    )
            if legacy_run_date:
                # Rename only the old field; keep all run ids and ticket links.
                with connection:
                    connection.execute("ALTER TABLE run RENAME COLUMN run_date TO date")
            return
    finally:
        connection.close()
    create_database(db_path)


def hash_password(plain_text_password: str) -> str:
    """Return a SHA-256 hash for the supplied password."""
    return hashlib.sha256(plain_text_password.encode("utf-8")).hexdigest()


# deliberately rebuild the canonical assignment database for setup and testing
def create_database(db_path: str | Path = DB_PATH) -> None:
    """Explicitly reset all booking data and seed the six assignment tables.

    This destructive operation is for setup/tests, never normal startup. Legacy
    table names are removed here so an explicit reset leaves only one schema.
    """
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()

        # Reset inside one transaction so a failure cannot leave a partial seed.
        cursor.executescript(
            """
            BEGIN IMMEDIATE;

            -- Clean up obsolete tables from the earlier implementation.
            DROP TABLE IF EXISTS tickets;
            DROP TABLE IF EXISTS buses;
            DROP TABLE IF EXISTS runs;
            DROP TABLE IF EXISTS bus_models;
            DROP TABLE IF EXISTS services;
            DROP TABLE IF EXISTS users;

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
                date TEXT NOT NULL,
                FOREIGN KEY (service_id) REFERENCES service (id),
                UNIQUE (service_id, date)
            );

            CREATE TABLE bus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                bus_model_id INTEGER NOT NULL,
                schedule_type TEXT NOT NULL CHECK (schedule_type IN ('weekend', 'workday')),
                FOREIGN KEY (service_id) REFERENCES service (id),
                FOREIGN KEY (bus_model_id) REFERENCES bus_model (id),
                UNIQUE (service_id, schedule_type)
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
        for day_offset in range(RUN_DAYS):
            run_day = (start + timedelta(days=day_offset)).isoformat()
            for service_id in service_ids:
                run_rows.append((service_id, run_day))
        cursor.executemany("INSERT INTO run (service_id, date) VALUES (?, ?)", run_rows)

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
            "SELECT id FROM run WHERE service_id = ? AND date = ? ORDER BY id LIMIT 1",
            (letterkenny_id, tomorrow),
        ).fetchone()[0]
        # NOTE: Initial ticket proves ticket->run->service relationship in seed data.
        cursor.execute("INSERT INTO ticket (user_id, run_id, number) VALUES (?, ?, ?)", (bob_id, run_id, 1))

        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


# provide a simple script entry point for creating and seeding the database
def main() -> None:
    """Run database creation and print a short confirmation message."""
    # NOTE: Run this script first before running test_database.py.
    create_database()
    print("Created and seeded flyonwheels.db")


if __name__ == "__main__":
    main()
