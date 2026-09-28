"""Open flyonwheels.db and dump all table contents."""

# DEMO NOTE: Use this script live in the video to prove persistence state.

import sqlite3
from pathlib import Path
from typing import List, Tuple

from create_database import DB_PATH

# prompt: list every user-defined table in the SQLite database

def get_table_names(connection: sqlite3.Connection) -> List[str]:
    """Return all non-system table names sorted alphabetically."""
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [row[0] for row in cursor.fetchall()]


# prompt: fetch all rows and column headers from a selected table
def get_table_data(connection: sqlite3.Connection, table_name: str) -> Tuple[List[str], List[tuple]]:
    """Return column names and all rows from the given table."""
    cursor = connection.cursor()
    # PRAGMA table_info returns one row per column definition.
    quoted_name = '"' + table_name.replace('"', '""') + '"'
    cursor.execute(f"PRAGMA table_info({quoted_name})")
    columns = [row[1] for row in cursor.fetchall()]

    cursor.execute(f"SELECT * FROM {quoted_name}")
    rows = cursor.fetchall()
    return columns, rows


# prompt: print one table section with its columns and row values for demo output
def print_table_dump(table_name: str, columns: List[str], rows: List[tuple]) -> None:
    """Print a readable dump for one database table."""
    # DEMO NOTE: Each printed section maps to one class/table in your diagram.
    print(f"\n=== TABLE: {table_name} ===")
    print(" | ".join(columns))
    if not rows:
        print("<no rows>")
        return
    for row in rows:
        print(" | ".join(str(value) for value in row))


# prompt: open flyonwheels db and dump all tables to standard output
def dump_database(db_path: str | Path = DB_PATH) -> None:
    """Print existing table data without creating or modifying the database."""
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        table_names = get_table_names(connection)
        if not table_names:
            print("No tables found.")
            return
        # Dump every user table so the full seeded state is visible.
        # DEMO NOTE: Use this output to verify required row counts and links.
        for table_name in table_names:
            columns, rows = get_table_data(connection, table_name)
            print_table_dump(table_name, columns, rows)
    finally:
        connection.close()


# prompt: run the database dump script directly from the command line
def main() -> None:
    """Execute the complete database dump routine."""
    dump_database()


if __name__ == "__main__":
    main()
