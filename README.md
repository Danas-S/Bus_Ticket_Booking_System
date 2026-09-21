# Bus_Ticket_Booking_System

Statement of provenance: The code content in this repository was written with the assistance of GitHub Copilot.

## What Is Included
- `create_database.py`: creates and seeds `flyonwheels.db`
- `test_database.py`: dumps all tables and rows from `flyonwheels.db`
- `user.py`: `User` class
- `service.py`: `Service` class
- `run.py`: `Run` class
- `bus_model.py`: `BusModel` class
- `bus.py`: `Bus` class
- `ticket.py`: `Ticket` class

## Class Diagram Photo
Add your class diagram image file in this folder, for example:
- `class_diagram.jpg`

## Class-to-Table Mapping
- `User` -> `users`
- `Service` -> `services`
- `Run` -> `runs`
- `BusModel` -> `bus_models`
- `Bus` -> `buses`
- `Ticket` -> `tickets`

## Relationship Notes (for demo explanation)
- One `Service` has many `Run` rows.
- One `Service` has physical `Bus` assignments.
- One `Bus` links to one `BusModel`.
- One `User` can own many `Ticket` rows.
- One `Ticket` belongs to one `Run`.

## How To Run
From repository root:

```powershell
c:/Users/Danas/FlyOnWheels_Bus_Ticket_Booking_System/.venv/Scripts/python.exe create_database.py
c:/Users/Danas/FlyOnWheels_Bus_Ticket_Booking_System/.venv/Scripts/python.exe test_database.py
```

## Expected Seed Summary
- 1 admin user (`Bob`) with hashed password from `pqr123#!`
- 3 services
- 2 bus models (`A` with 30 seats, `B` with 50 seats)
- 7 days of runs from today for each service
- 2 buses per service (`A` for weekend, `B` for workday)
- 1 ticket for Bob on tomorrow's Dublin to Letterkenny run
