"""Menu-driven transport booking application for Week 10 Part 2."""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from create_database import DB_PATH, RUN_DAYS, ensure_database_exists, hash_password
from bus import Bus
from bus_model import BusModel
from run import Run
from service import Service
from ticket import Ticket
from user import User

# NOTE: This file is split into three layers:
# 1) data/auth helpers, 2) print helpers, 3) menu controllers.


@dataclass
class RunDetails:
    """Group a dated run with its service, assigned bus, capacity and availability."""

    run: Run
    service: Service
    bus: Bus
    bus_model: BusModel
    available_seats: int


@dataclass
class TicketDetails:
    """Group a booking with the run and service shown in ticket history."""

    ticket: Ticket
    run: Run
    service: Service


# open sqlite connection for the booking database and return it to callers
def open_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Create and return a SQLite connection for the transport system database."""
    connection = sqlite3.connect(db_path)
    # NOTE: Row objects allow readable access like row["username"].
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# validate login credentials against stored username and password hash
def authenticate_user(
    connection: sqlite3.Connection, username: str, password: str
) -> User | None:
    """Return a User with its stored hash and role, or None for invalid credentials."""
    password_hash = hash_password(password)
    cursor = connection.execute(
        "SELECT id, username, password, admin FROM user WHERE username = ? AND password = ?",
        (username, password_hash),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return User(row["id"], row["username"], row["password"], bool(row["admin"]))


# create a regular customer account and return whether creation succeeded
def create_account(connection: sqlite3.Connection, username: str, password: str) -> bool:
    """Insert a non-admin user account and return True on success, else False."""
    cleaned_username = username.strip()
    if not cleaned_username or not password:
        return False

    try:
        connection.execute(
            "INSERT INTO user (username, password, admin) VALUES (?, ?, ?)",
            (cleaned_username, hash_password(password), 0),
        )
        connection.commit()
        return True
    except sqlite3.IntegrityError:
        return False


# fetch all services in a stable order for admin and user display screens
def list_services(connection: sqlite3.Connection) -> list[Service]:
    """Return Service objects ordered by database id."""
    cursor = connection.execute("SELECT id, name FROM service ORDER BY id")
    return [Service(row["id"], row["name"]) for row in cursor.fetchall()]


# create a new service and automatically generate its runs and bus assignments
def create_service(connection: sqlite3.Connection, service_name: str) -> bool:
    """Insert a service, seven runs, and two bus rows; return True when successful."""
    cleaned_name = service_name.strip()
    if not cleaned_name:
        return False

    try:
        cursor = connection.execute(
            "INSERT INTO service (name) VALUES (?)",
            (cleaned_name,),
        )
        service_id = cursor.lastrowid

        start_day = date.today()
        # NOTE: Every new service is immediately usable for the next 7 days.
        run_rows = [
            (service_id, (start_day + timedelta(days=offset)).isoformat())
            for offset in range(RUN_DAYS)
        ]
        connection.executemany(
            "INSERT INTO run (service_id, date) VALUES (?, ?)",
            run_rows,
        )

        model_rows = connection.execute(
            "SELECT id, name FROM bus_model WHERE name IN ('A', 'B')"
        ).fetchall()
        model_map = {row["name"]: row["id"] for row in model_rows}
        if "A" not in model_map or "B" not in model_map:
            connection.rollback()
            return False

        bus_rows = [
            (service_id, model_map["A"], "weekend"),
            (service_id, model_map["B"], "workday"),
        ]
        connection.executemany(
            "INSERT INTO bus (service_id, bus_model_id, schedule_type) VALUES (?, ?, ?)",
            bus_rows,
        )

        connection.commit()
        return True
    except sqlite3.IntegrityError:
        connection.rollback()
        return False


# list future runs with dynamic seat availability for customer booking choices
def list_future_runs(connection: sqlite3.Connection) -> list[RunDetails]:
    """Return today's/upcoming runs with assigned buses and SQL seat totals."""
    today_text = date.today().isoformat()
    query = """
        SELECT
            r.id AS run_id,
            r.service_id,
            r.date,
            s.name AS service_name,
            b.id AS bus_id,
            b.schedule_type,
            bm.id AS model_id,
            bm.name AS model_name,
            bm.seats,
            bm.seats - COALESCE(SUM(t.number), 0) AS available_seats
        FROM run r
        JOIN service s ON s.id = r.service_id
        JOIN bus b
            ON b.service_id = r.service_id
            AND (
                (b.schedule_type = 'weekend' AND CAST(strftime('%w', r.date) AS INTEGER) IN (0, 6))
                OR (b.schedule_type = 'workday' AND CAST(strftime('%w', r.date) AS INTEGER) BETWEEN 1 AND 5)
            )
        JOIN bus_model bm ON bm.id = b.bus_model_id
        LEFT JOIN ticket t ON t.run_id = r.id
        WHERE r.date >= ?
        GROUP BY r.id, b.id
        ORDER BY r.date, s.name, r.id
    """
    # NOTE: This query computes dynamic availability: capacity - sold tickets.
    return [
        RunDetails(
            Run(row["run_id"], row["service_id"], row["date"]),
            Service(row["service_id"], row["service_name"]),
            Bus(row["bus_id"], row["service_id"], row["model_id"], row["schedule_type"]),
            BusModel(row["model_id"], row["model_name"], row["seats"]),
            row["available_seats"],
        )
        for row in connection.execute(query, (today_text,))
    ]


# book tickets for a selected run while enforcing seat availability and user cancellation
def buy_tickets(
    connection: sqlite3.Connection,
    user_id: int,
    run_id: int,
    number_of_tickets: int,
    confirmation_text: str,
) -> str:
    """Try to buy tickets and return result text for confirmed, cancelled, or invalid cases."""
    if number_of_tickets <= 0:
        return "Invalid number of tickets."

    runs = list_future_runs(connection)
    target_run = next((details for details in runs if details.run.id == run_id), None)
    if target_run is None:
        return "Invalid run selection."

    if target_run.available_seats < number_of_tickets:
        return "Not enough seats available."

    if confirmation_text.strip().lower() == "esc":
        return "Booking cancelled."

    # NOTE: We store quantity in one row (`number`) for simpler ticket summaries.
    connection.execute(
        "INSERT INTO ticket (user_id, run_id, number) VALUES (?, ?, ?)",
        (user_id, run_id, number_of_tickets),
    )
    connection.commit()
    return "Booking confirmed!"


# retrieve all tickets bought by a user so they can view their booking history
def list_user_tickets(connection: sqlite3.Connection, user_id: int) -> list[TicketDetails]:
    """Return one user's Ticket objects with their dated Run and Service."""
    query = """
        SELECT
            t.id AS ticket_id,
            t.user_id,
            t.run_id,
            t.number,
            r.service_id,
            r.date,
            s.name AS service_name
        FROM ticket t
        JOIN run r ON r.id = t.run_id
        JOIN service s ON s.id = r.service_id
        WHERE t.user_id = ?
        ORDER BY r.date, t.id
    """
    return [
        TicketDetails(
            Ticket(row["ticket_id"], row["user_id"], row["run_id"], row["number"]),
            Run(row["run_id"], row["service_id"], row["date"]),
            Service(row["service_id"], row["service_name"]),
        )
        for row in connection.execute(query, (user_id,))
    ]


# display service rows in a readable format for admin and customer menus
def print_services(services: list[Service]) -> None:
    """Print a numbered list of services or a fallback message when empty."""
    if not services:
        print("No services available.")
        return
    for service in services:
        print(f"{service.id}. {service.name}")


# show future run options with availability so users can select booking targets
def print_future_runs(runs: list[RunDetails]) -> None:
    """Print dated runs, service names, assigned buses and remaining capacity."""
    if not runs:
        print("No future runs available.")
        return
    for details in runs:
        print(
            f"Run {details.run.id}: {details.run.date} | "
            f"{details.service.name} | seats left: {details.available_seats} | "
            f"Bus {details.bus.id}: model {details.bus_model.name} "
            f"({details.bus_model.seats} seats, {details.bus.schedule_type})"
        )


# print purchased tickets so customers can review what they already booked
def print_user_tickets(tickets: list[TicketDetails]) -> None:
    """Print each Ticket's quantity with its Run date and Service name."""
    if not tickets:
        print("No tickets purchased yet.")
        return
    for details in tickets:
        print(
            f"Ticket {details.ticket.id}: {details.ticket.number} seat(s) | "
            f"{details.run.date} | {details.service.name}"
        )


# run the logged-in admin menu loop for service viewing and creation tasks
def admin_menu(connection: sqlite3.Connection) -> None:
    """Show admin options until logout is selected."""
    while True:
        print("\n=== Admin Menu ===")
        print("1. View services")
        print("2. Create a service")
        print("3. Log out")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            print_services(list_services(connection))
        elif choice == "2":
            service_name = input("Enter service name: ").strip()
            if create_service(connection, service_name):
                print(f"Service '{service_name}' created.")
            else:
                print("Service could not be created.")
        elif choice == "3":
            return
        else:
            print("Invalid option.")


# run the logged-in customer menu loop for browsing runs and managing bookings
def customer_menu(connection: sqlite3.Connection, user: User) -> None:
    """Show customer options until logout is selected."""
    while True:
        print("\n=== Customer Menu ===")
        print("1. View future bus runs")
        print("2. Buy tickets")
        print("3. View my tickets")
        print("4. Log out")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            print_future_runs(list_future_runs(connection))
        elif choice == "2":
            runs = list_future_runs(connection)
            print_future_runs(runs)
            if not runs:
                continue

            run_text = input("Select run number: ").strip()
            ticket_count_text = input("Number of tickets: ").strip()
            try:
                selected_index = int(run_text)
                ticket_count = int(ticket_count_text)
            except ValueError:
                print("Invalid numeric input.")
                continue

            if selected_index < 1 or selected_index > len(runs):
                print("Invalid run selection.")
                continue

            # NOTE: User input selects list position, then maps to real DB run_id.
            selected_run = runs[selected_index - 1]
            run_id = selected_run.run.id

            if ticket_count <= 0:
                print("Invalid number of tickets.")
                continue

            if selected_run.available_seats < ticket_count:
                print("Not enough seats available.")
                continue

            confirm_text = input("Press Enter to confirm or type 'esc' to cancel: ")
            result_message = buy_tickets(connection, user.id, run_id, ticket_count, confirm_text)
            print(result_message)
        elif choice == "3":
            print_user_tickets(list_user_tickets(connection, user.id))
        elif choice == "4":
            return
        else:
            print("Invalid option.")


# run the home menu loop for login account creation and program exit behavior
def home_menu(connection: sqlite3.Connection) -> None:
    """Show the home menu and route users to admin or customer workflows."""
    while True:
        print("\n=== Transport Booking System ===")
        print("1. Log in")
        print("2. Create an account")
        print("3. Exit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            username = input("Username: ").strip()
            password = input("Password: ")
            user = authenticate_user(connection, username, password)
            if user is None:
                print("Invalid username or password.")
                continue

            print(f"Welcome back, {user.username}!")
            # DEMO NOTE: Role-based routing is controlled by the admin flag.
            if user.admin:
                admin_menu(connection)
            else:
                customer_menu(connection, user)
        elif choice == "2":
            username = input("Choose username: ").strip()
            password = input("Choose password: ")
            if create_account(connection, username, password):
                print(f"Account created for '{username}'.")
            else:
                print("Account could not be created.")
        elif choice == "3":
            return
        else:
            print("Invalid option.")


# start the application by preparing data and running the home menu loop
def main(db_path: str | Path = DB_PATH) -> None:
    """Initialize the database if needed and launch menus, preserving saved data."""
    ensure_database_exists(db_path)
    connection = open_connection(db_path)
    try:
        home_menu(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
