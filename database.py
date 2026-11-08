
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.environ.get(
        "PARKING_DB_PATH",
        str(Path(__file__).with_name("parking.db"))
    )
)


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def table_exists(connection, table_name):
    return connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,)
    ).fetchone() is not None


def get_columns(connection, table_name):
    return {
        row["name"]
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


def migrate_settings(connection):
    if not table_exists(connection, "settings"):
        connection.execute("""
            CREATE TABLE settings (
                browser_id TEXT NOT NULL,
                setting_key TEXT NOT NULL,
                setting_value TEXT NOT NULL,
                PRIMARY KEY (browser_id, setting_key)
            )
        """)
        return

    columns = get_columns(connection, "settings")

    if not {"setting_key", "setting_value"}.issubset(columns):
        raise RuntimeError("Unexpected settings table structure.")

    connection.execute("DROP TABLE IF EXISTS settings_migration")

    connection.execute("""
        CREATE TABLE settings_migration (
            browser_id TEXT NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL,
            PRIMARY KEY (browser_id, setting_key)
        )
    """)

    if "browser_id" in columns:
        connection.execute("""
            INSERT OR REPLACE INTO settings_migration
            (browser_id, setting_key, setting_value)
            SELECT
                COALESCE(NULLIF(browser_id, ''), 'legacy'),
                setting_key,
                setting_value
            FROM settings
        """)
    else:
        connection.execute("""
            INSERT OR REPLACE INTO settings_migration
            (browser_id, setting_key, setting_value)
            SELECT 'legacy', setting_key, setting_value
            FROM settings
        """)

    connection.execute("DROP TABLE settings")
    connection.execute("""
        ALTER TABLE settings_migration RENAME TO settings
    """)


def migrate_parking_records(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS parking_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            browser_id TEXT NOT NULL DEFAULT 'legacy',
            vehicle_number TEXT NOT NULL,
            slot_number INTEGER,
            arrival_time TEXT NOT NULL,
            entry_time TEXT,
            exit_time TEXT,
            status TEXT NOT NULL
        )
    """)

    columns = get_columns(connection, "parking_records")

    if "browser_id" not in columns:
        connection.execute("""
            ALTER TABLE parking_records
            ADD COLUMN browser_id TEXT NOT NULL DEFAULT 'legacy'
        """)

    required = {
        "id", "browser_id", "vehicle_number", "slot_number",
        "arrival_time", "entry_time", "exit_time", "status"
    }

    if not required.issubset(get_columns(connection, "parking_records")):
        raise RuntimeError("Unexpected parking_records table structure.")


def migrate_activity_log(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            browser_id TEXT NOT NULL DEFAULT 'legacy',
            event_time TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)

    columns = get_columns(connection, "activity_log")

    if "browser_id" not in columns:
        connection.execute("""
            ALTER TABLE activity_log
            ADD COLUMN browser_id TEXT NOT NULL DEFAULT 'legacy'
        """)

    required = {"id", "browser_id", "event_time", "message"}

    if not required.issubset(get_columns(connection, "activity_log")):
        raise RuntimeError("Unexpected activity_log table structure.")


def initialize_database():
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        migrate_settings(connection)
        migrate_parking_records(connection)
        migrate_activity_log(connection)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                browser_id TEXT NOT NULL,
                log_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_parking_browser
            ON parking_records(browser_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_browser
            ON activity_log(browser_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_settings_browser
            ON settings(browser_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_system_logs_browser
            ON system_logs(browser_id, log_type, id)
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
