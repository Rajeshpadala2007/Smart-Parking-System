
import threading
from collections import deque
from datetime import datetime

from database import get_connection


class ParkingSystem:

    def __init__(self, browser_id):
        self.browser_id = browser_id

        self.lock = threading.Lock()

        self.thread_logs = []
        self.mutex_logs = []
        self.semaphore_logs = []

        self.slots = {}
        self.waiting_queue = deque()
        self.total_slots = 5

        self._restore_from_database()
        self._restore_system_logs()

        occupied = sum(
            1 for vehicle in self.slots.values() if vehicle is not None
        )

        self.semaphore = threading.Semaphore(
            max(0, self.total_slots - occupied)
        )

    def now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --------------------------------------------------
    # ACTIVITY LOGS
    # --------------------------------------------------

    def log_activity(self, message):
        connection = get_connection()

        try:
            connection.execute("""
                INSERT INTO activity_log
                (browser_id, event_time, message)
                VALUES (?, ?, ?)
            """, (
                self.browser_id,
                self.now(),
                message
            ))

            connection.commit()

        finally:
            connection.close()

    # --------------------------------------------------
    # PERSISTENT THREAD / MUTEX / SEMAPHORE LOGS
    # --------------------------------------------------

    def _write_system_log(self, log_type, message):
        event_time = self.now()

        connection = get_connection()

        try:
            connection.execute("""
                INSERT INTO system_logs
                (browser_id, log_type, event_time, message)
                VALUES (?, ?, ?, ?)
            """, (
                self.browser_id,
                log_type,
                event_time,
                message
            ))

            connection.commit()

        finally:
            connection.close()

        formatted_message = f"{event_time} - {message}"

        if log_type == "thread":
            self.thread_logs.append(formatted_message)
            self.thread_logs = self.thread_logs[-100:]

        elif log_type == "mutex":
            self.mutex_logs.append(formatted_message)
            self.mutex_logs = self.mutex_logs[-100:]

        elif log_type == "semaphore":
            self.semaphore_logs.append(formatted_message)
            self.semaphore_logs = self.semaphore_logs[-100:]

    def _restore_system_logs(self):
        connection = get_connection()

        try:
            for log_type, attribute in (
                ("thread", "thread_logs"),
                ("mutex", "mutex_logs"),
                ("semaphore", "semaphore_logs")
            ):
                rows = connection.execute("""
                    SELECT event_time, message
                    FROM system_logs
                    WHERE browser_id = ?
                    AND log_type = ?
                    ORDER BY id DESC
                    LIMIT 100
                """, (
                    self.browser_id,
                    log_type
                )).fetchall()

                logs = [
                    f"{row['event_time']} - {row['message']}"
                    for row in reversed(rows)
                ]

                setattr(self, attribute, logs)

        finally:
            connection.close()

    # --------------------------------------------------
    # RESTORE PARKING DATA
    # --------------------------------------------------

    def _restore_from_database(self):
        connection = get_connection()

        try:
            connection.execute("""
                INSERT OR IGNORE INTO settings
                (browser_id, setting_key, setting_value)
                VALUES (?, 'total_slots', '5')
            """, (self.browser_id,))

            setting = connection.execute("""
                SELECT setting_value
                FROM settings
                WHERE browser_id = ?
                AND setting_key = 'total_slots'
            """, (self.browser_id,)).fetchone()

            if setting:
                self.total_slots = int(setting["setting_value"])

            if self.total_slots < 1:
                self.total_slots = 5

            self.slots = {
                number: None
                for number in range(1, self.total_slots + 1)
            }

            records = connection.execute("""
                SELECT *
                FROM parking_records
                WHERE browser_id = ?
                AND status IN ('Parked', 'Waiting')
                ORDER BY id ASC
            """, (self.browser_id,)).fetchall()

            for record in records:

                item = {
                    "vehicle_number": record["vehicle_number"],
                    "record_id": record["id"]
                }

                slot = record["slot_number"]

                if (
                    record["status"] == "Parked"
                    and slot in self.slots
                    and self.slots[slot] is None
                ):
                    self.slots[slot] = item

                else:
                    self.waiting_queue.append(item)

                    # Keep database status consistent with restored queue.
                    connection.execute("""
                        UPDATE parking_records
                        SET slot_number = NULL,
                            status = 'Waiting'
                        WHERE id = ?
                        AND browser_id = ?
                    """, (
                        record["id"],
                        self.browser_id
                    ))

            connection.commit()

        finally:
            connection.close()

    # --------------------------------------------------
    # VEHICLE ENTRY
    # --------------------------------------------------

    def add_vehicle(self, vehicle_number):
        vehicle_number = vehicle_number.strip().upper()

        if not vehicle_number:
            return {
                "success": False,
                "message": "Enter vehicle number."
            }

        thread = threading.Thread(
            target=self._process_vehicle,
            args=(vehicle_number,),
            daemon=True
        )

        thread.start()

        return {
            "success": True,
            "message": (
                f"Vehicle {vehicle_number} arrival received. "
                "Processing thread started."
            )
        }

    def _process_vehicle(self, vehicle_number):

        with self.lock:

            self._write_system_log(
                "thread",
                f"Thread started for {vehicle_number}"
            )

            self._write_system_log(
                "mutex",
                f"Mutex lock acquired for {vehicle_number}"
            )

            try:
                connection = get_connection()

                try:
                    duplicate = connection.execute("""
                        SELECT id
                        FROM parking_records
                        WHERE browser_id = ?
                        AND UPPER(vehicle_number) = ?
                        AND status IN ('Parked', 'Waiting')
                        LIMIT 1
                    """, (
                        self.browser_id,
                        vehicle_number
                    )).fetchone()

                    if duplicate:
                        message = (
                            f"Duplicate vehicle {vehicle_number} rejected."
                        )

                    else:
                        cursor = connection.execute("""
                            INSERT INTO parking_records
                            (
                                browser_id,
                                vehicle_number,
                                slot_number,
                                arrival_time,
                                entry_time,
                                exit_time,
                                status
                            )
                            VALUES (?, ?, NULL, ?, NULL, NULL, 'Waiting')
                        """, (
                            self.browser_id,
                            vehicle_number,
                            self.now()
                        ))

                        record_id = cursor.lastrowid
                        connection.commit()
                        message = None

                finally:
                    connection.close()

                if message:
                    self._write_system_log(
                        "thread",
                        f"Duplicate vehicle rejected: {vehicle_number}"
                    )

                    self.log_activity(message)

                    return

                item = {
                    "vehicle_number": vehicle_number,
                    "record_id": record_id
                }

                if self.semaphore.acquire(blocking=False):

                    free_slot = next(
                        (
                            number
                            for number, vehicle in self.slots.items()
                            if vehicle is None
                        ),
                        None
                    )

                    if free_slot is None:
                        self.semaphore.release()
                        self.waiting_queue.append(item)

                        message = (
                            f"{vehicle_number} added to waiting queue."
                        )

                    else:
                        self.slots[free_slot] = item

                        connection = get_connection()

                        try:
                            connection.execute("""
                                UPDATE parking_records
                                SET slot_number = ?,
                                    entry_time = ?,
                                    status = 'Parked'
                                WHERE id = ?
                                AND browser_id = ?
                            """, (
                                free_slot,
                                self.now(),
                                record_id,
                                self.browser_id
                            ))

                            connection.commit()

                        finally:
                            connection.close()

                        message = (
                            f"{vehicle_number} parked in slot {free_slot}."
                        )

                        self._write_system_log(
                            "semaphore",
                            f"Semaphore permit acquired by {vehicle_number}"
                        )

                else:
                    self.waiting_queue.append(item)

                    message = (
                        f"{vehicle_number} added to FIFO waiting queue."
                    )

                self.log_activity(message)

            finally:
                self._write_system_log(
                    "thread",
                    f"Thread completed for {vehicle_number}"
                )

                self._write_system_log(
                    "mutex",
                    "Mutex lock released"
                )

    # --------------------------------------------------
    # VEHICLE EXIT
    # --------------------------------------------------

    def exit_vehicle(self, slot_number):

        with self.lock:

            if slot_number not in self.slots:
                return {
                    "success": False,
                    "message": "Invalid parking slot."
                }

            vehicle = self.slots[slot_number]

            if vehicle is None:
                return {
                    "success": False,
                    "message": "This parking slot is already empty."
                }

            vehicle_number = vehicle["vehicle_number"]

            connection = get_connection()

            try:
                connection.execute("""
                    UPDATE parking_records
                    SET exit_time = ?,
                        status = 'Exited'
                    WHERE id = ?
                    AND browser_id = ?
                """, (
                    self.now(),
                    vehicle["record_id"],
                    self.browser_id
                ))

                connection.commit()

            finally:
                connection.close()

            if self.waiting_queue:

                next_vehicle = self.waiting_queue.popleft()

                self.slots[slot_number] = next_vehicle

                connection = get_connection()

                try:
                    connection.execute("""
                        UPDATE parking_records
                        SET slot_number = ?,
                            entry_time = ?,
                            status = 'Parked'
                        WHERE id = ?
                        AND browser_id = ?
                    """, (
                        slot_number,
                        self.now(),
                        next_vehicle["record_id"],
                        self.browser_id
                    ))

                    connection.commit()

                finally:
                    connection.close()

                message = (
                    f"{vehicle_number} exited. "
                    f"{next_vehicle['vehicle_number']} assigned "
                    f"to slot {slot_number}."
                )

                self._write_system_log(
                    "semaphore",
                    "Existing semaphore permit transferred "
                    "to waiting vehicle"
                )

            else:

                self.slots[slot_number] = None
                self.semaphore.release()

                self._write_system_log(
                    "semaphore",
                    "Semaphore permit released after vehicle exit"
                )

                message = (
                    f"{vehicle_number} exited from slot {slot_number}."
                )

            self.log_activity(message)

            return {
                "success": True,
                "message": message
            }

    # --------------------------------------------------
    # CHANGE PARKING CAPACITY
    # --------------------------------------------------

    def resize_slots(self, new_total):

        with self.lock:

            if new_total < 1:
                return {
                    "success": False,
                    "message": "At least one parking slot is required."
                }

            # Do not remove a slot that contains a parked vehicle.
            occupied_removed_slots = [
                number
                for number, vehicle in self.slots.items()
                if number > new_total and vehicle is not None
            ]

            if occupied_removed_slots:
                return {
                    "success": False,
                    "message": (
                        "Cannot reduce capacity because vehicles are "
                        "parked in slots: "
                        + ", ".join(map(str, occupied_removed_slots))
                    )
                }

            old_slots = self.slots

            self.slots = {
                number: old_slots.get(number)
                for number in range(1, new_total + 1)
            }

            self.total_slots = new_total

            # Fill newly available slots from the FIFO queue.
            while self.waiting_queue:

                free_slot = next(
                    (
                        number
                        for number, vehicle in self.slots.items()
                        if vehicle is None
                    ),
                    None
                )

                if free_slot is None:
                    break

                next_vehicle = self.waiting_queue.popleft()

                connection = get_connection()

                try:
                    connection.execute("""
                        UPDATE parking_records
                        SET slot_number = ?,
                            entry_time = ?,
                            status = 'Parked'
                        WHERE id = ?
                        AND browser_id = ?
                    """, (
                        free_slot,
                        self.now(),
                        next_vehicle["record_id"],
                        self.browser_id
                    ))

                    connection.commit()

                finally:
                    connection.close()

                self.slots[free_slot] = next_vehicle

            occupied_now = sum(
                1 for vehicle in self.slots.values()
                if vehicle is not None
            )

            self.semaphore = threading.Semaphore(
                new_total - occupied_now
            )

            connection = get_connection()

            try:
                connection.execute("""
                    INSERT INTO settings
                    (browser_id, setting_key, setting_value)
                    VALUES (?, 'total_slots', ?)
                    ON CONFLICT(browser_id, setting_key)
                    DO UPDATE SET setting_value = excluded.setting_value
                """, (
                    self.browser_id,
                    str(new_total)
                ))

                connection.commit()

            finally:
                connection.close()

            message = (
                f"Parking capacity changed to {new_total} slots."
            )

            self.log_activity(message)

            return {
                "success": True,
                "message": message
            }

    # --------------------------------------------------
    # DASHBOARD STATE
    # --------------------------------------------------

    def get_state(self):

        with self.lock:

            occupied = sum(
                1 for vehicle in self.slots.values()
                if vehicle is not None
            )

            slots_data = []

            for number, vehicle in self.slots.items():

                slots_data.append({
                    "slot_number": number,
                    "vehicle_number": (
                        vehicle["vehicle_number"] if vehicle else None
                    ),
                    "status": (
                        "Occupied" if vehicle else "Available"
                    )
                })

            connection = get_connection()

            try:
                records = connection.execute("""
                    SELECT *
                    FROM parking_records
                    WHERE browser_id = ?
                    ORDER BY id DESC
                    LIMIT 100
                """, (self.browser_id,)).fetchall()

                activities = connection.execute("""
                    SELECT *
                    FROM activity_log
                    WHERE browser_id = ?
                    ORDER BY id DESC
                    LIMIT 100
                """, (self.browser_id,)).fetchall()

                database_records = [
                    dict(row) for row in records
                ]

                activity_logs = [
                    dict(row) for row in activities
                ]

            finally:
                connection.close()

            return {
                "total_slots": self.total_slots,
                "occupied_slots": occupied,
                "available_slots": self.total_slots - occupied,
                "waiting_count": len(self.waiting_queue),
                "slots": slots_data,
                "waiting_queue": [
                    item["vehicle_number"]
                    for item in self.waiting_queue
                ],
                "thread_logs": self.thread_logs[-100:],
                "mutex_logs": self.mutex_logs[-100:],
                "semaphore_logs": self.semaphore_logs[-100:],
                "activity_logs": activity_logs,
                "database_records": database_records
            }
