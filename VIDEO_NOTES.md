# Week 10 video evidence

Use these as talking points, not a script to read. The pre-correction baseline is commit `602eaff`; `git show 602eaff:main.py` and `git show 602eaff:create_database.py` show the original code. No old history or lecturer assertions were rewritten.

## Problems fixed: before, why, fix, proof

### 1. Destructive startup (strongest example)

- **Before:** `main.main()` called `create_database()` on every launch, which dropped/reseeded tables. Accounts, services and bookings disappeared after exit/restart.
- **Why:** SQLite persistence was defeated by the startup algorithm.
- **Fix:** `main.main()` calls `create_database.ensure_database_exists()`. Missing/empty databases initialize once; existing data is reused. Unknown schemas are refused instead of erased. Explicit reset remains available.
- **Proof:** `TestPersistence.test_account_and_booking_survive_startup` and `test_real_process_restart_preserves_account_service_and_booking`. The latter launches unmodified `main.py` twice and verifies login, service and two-seat booking through both output and SQL-backed objects.
- **Visible demo:** create a customer, buy two seats, exit, launch again, log in and view the same booking. Never run the reset script/tests between those launches.

### 2. Duplicate and inconsistent schema (second strongest example)

- **Before:** `create_database.py` contained independent plural and singular creation/seed paths. Running it as a script populated different tables from the imported `create_database()` function. The original database contained both sets.
- **Why:** dead/duplicated code and conflicting field meanings made models, setup and Part 2 disagree.
- **Fix:** one singular schema and one explicit creation function. `Ticket.number` now means booking quantity; `Run.date` matches lecturer screenshot 9. The old singular date field is renamed without dropping records. Only an explicit reset removes obsolete plural tables.
- **Proof:** `python create_database.py`, then `python test_database.py`: six tables; 1 user, 3 services, 2 models, 21 runs, 6 buses and 1 ticket. `test_seed_schema_and_relationships` checks the data/links; the migration test preserves existing tickets.

### 3. Part 1 objects were not used

- **Before:** `main.py` passed raw SQLite rows through the menus and never used the six Part 1 classes, contrary to lecturer screenshot 10.
- **Fix:** `authenticate_user`, `list_services`, `list_future_runs` and `list_user_tickets` now return/use model objects. `RunDetails` and `TicketDetails` simply group related objects for display. SQL still calculates availability.
- **Proof:** show `User.admin` controlling the menu, `Run.id` selecting the purchase, bus/model details in listings and `Ticket.number` in history. `test_booking_updates_availability_and_uses_models` checks the types and quantity reduction.

Other concrete fixes: `print_future_runs()` now displays the list positions accepted by `customer_menu()`; whitespace-only passwords are rejected; duplicate-account failures roll back; booking capacity checks/inserts run in one transaction to prevent overselling.

## Quality already present in the baseline: choose at least two

All candidates below are visible in `602eaff:main.py`, not invented after refactoring.

| Original code | Why it was already good |
| --- | --- |
| `authenticate_user()`, `create_account()`, `create_service()` | Parameterized SQL binds user text separately from SQL syntax. |
| `create_account()` and `create_service()` | Specific `sqlite3.IntegrityError` handling reports duplicate/constraint failures rather than hiding every exception. |
| `main()` | A `finally` block closes the database connection even if the menu fails. |
| `list_future_runs()` | Correct date-based bus selection and SQL capacity minus summed booking quantities; no hard-coded remaining-seat count. |
| `create_service()` | Generates seven dates dynamically and both bus assignments, rolling back an incomplete service. |
| `home_menu()`, `admin_menu()`, `customer_menu()` | Clear role-based routing and separation of menu control from data/print helpers. |

Show parameterized SQL and dynamic capacity for two complementary examples. Explain that these sound parts were preserved while the defects around them were fixed.

## Demonstration results

- `python -m unittest test_main.py -v`: 2 passed, supplied file unchanged.
- `python -m unittest discover -v`: 18 passed.
- `python create_database.py`: succeeded; `python test_database.py`: dumped the six canonical tables and required seed relationships.
- Two actual terminal launches: `RestartDemo` bought two seats in launch one, exited, then logged in and saw that booking in launch two. The saved row and non-admin account were checked programmatically. The delivery database was explicitly reseeded afterwards for a clean demo.
- SQLite integrity check returned `ok`; foreign-key check returned no violations. A copy of the original pre-edit database also retained every singular user/service/run/ticket record through the date-column migration.

The original database backup and restart logs are retained locally under `.git/week10-original.db`, `.git/week10-restart-first.txt` and `.git/week10-restart-second.txt`; they are not submission files.

## Nine-minute screencast outline

| Time | Show and explain |
| --- | --- |
| 0:00-0:45 | Purpose, original class diagram photo and clarified relationships in README. |
| 0:45-1:30 | Run database creation/dump; identify seed counts and a ticket-to-run-to-service link. |
| 1:30-3:20 | Admin/customer menus, a successful booking, cancellation and restart persistence. |
| 3:20-4:40 | Problem 1: old destructive call, new startup helper, why data survives. |
| 4:40-6:00 | Problem 2: old two-schema paths, canonical tables/fields; briefly show real model usage. |
| 6:00-7:10 | Two original positives with code references: SQL parameters and dynamic capacity. |
| 7:10-8:10 | Run lecturer/full tests and point out the restart/validation cases. Tests reset demo data, so run them after the persistence demonstration. |
| 8:10-9:00 | Meaningful Git commits, final branch/PR state, hashing and seven-day scope limitations. |

Stop at about **9:00**, leaving one minute below the strict 10-minute limit. Record a screencast without a presenter camera, upload it, and update `url_link.txt`. The existing URL is retained but does not establish that a new recording covers these corrections. Confirm the required module-repository `week10` location before submitting.
