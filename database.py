
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("parking.db")


def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_connection()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS parking_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_number TEXT NOT NULL,
                slot_number INTEGER,
                arrival_time TEXT NOT NULL,
                entry_time TEXT,
                exit_time TEXT,
                status TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)

        connection.execute("""
            INSERT OR IGNORE INTO settings
            (setting_key, setting_value)
            VALUES ('total_slots', '5')
        """)

        connection.commit()
        print("Database initialized successfully!")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
