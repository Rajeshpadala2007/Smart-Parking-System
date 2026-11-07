
import threading
from collections import deque
from datetime import datetime

from database import get_connection


class ParkingSystem:

    def __init__(self):
        self.lock = threading.Lock()
        self.thread_logs = []
        self.mutex_logs = []
        self.semaphore_logs = []
        self.slots = {}
        self.waiting_queue = deque()
        self.total_slots = 5

        self._restore_from_database()

        occupied = sum(1 for v in self.slots.values() if v)
        self.semaphore = threading.Semaphore(
            max(0, self.total_slots - occupied)
        )

    def now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def log_activity(self, message):
        connection = get_connection()
        try:
            connection.execute("""
                INSERT INTO activity_log (event_time, message)
                VALUES (?, ?)
            """, (self.now(), message))
            connection.commit()
        finally:
            connection.close()

    def _restore_from_database(self):
        connection = get_connection()

        try:
            setting = connection.execute("""
                SELECT setting_value
                FROM settings
                WHERE setting_key = 'total_slots'
            """).fetchone()

            if setting:
                self.total_slots = int(setting["setting_value"])

            self.slots = {
                i: None for i in range(1, self.total_slots + 1)
            }

            records = connection.execute("""
                SELECT *
                FROM parking_records
                WHERE status IN ('Parked', 'Waiting')
                ORDER BY id ASC
            """).fetchall()

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

        finally:
            connection.close()

    def add_vehicle(self, vehicle_number):
        vehicle_number = vehicle_number.strip().upper()

        if not vehicle_number:
            return {
                "success": False,
                "message": "Enter a vehicle number."
            }

        thread = threading.Thread(
            target=self._process_vehicle,
            args=(vehicle_number,),
            daemon=True
        )

        thread.start()

        return {
            "success": True,
            "message": f"Vehicle {vehicle_number} arrival received. Processing thread started."
        }

    def _process_vehicle(self, vehicle_number):

        with self.lock:
            self.thread_logs.append(
                f"{self.now()} - Thread started for {vehicle_number}"
            )

            self.mutex_logs.append(
                f"{self.now()} - Mutex lock acquired for {vehicle_number}"
            )

            connection = get_connection()

            try:
                duplicate = connection.execute("""
                    SELECT id
                    FROM parking_records
                    WHERE vehicle_number = ?
                    AND status IN ('Parked', 'Waiting')
                """, (vehicle_number,)).fetchone()

                if duplicate:
                    self.thread_logs.append(
                        f"{self.now()} - Duplicate vehicle rejected: {vehicle_number}"
                    )
                    self.log_activity(
                        f"Duplicate vehicle {vehicle_number} rejected."
                    )
                    return

                cursor = connection.execute("""
                    INSERT INTO parking_records
                    (vehicle_number, slot_number, arrival_time,
                     entry_time, exit_time, status)
                    VALUES (?, NULL, ?, NULL, NULL, 'Waiting')
                """, (vehicle_number, self.now()))

                record_id = cursor.lastrowid
                connection.commit()

            finally:
                connection.close()

            if self.semaphore.acquire(blocking=False):
                free_slot = next(
                    (
                        number for number, vehicle in self.slots.items()
                        if vehicle is None
                    ),
                    None
                )

                if free_slot is None:
                    self.semaphore.release()
                    self.waiting_queue.append({
                        "vehicle_number": vehicle_number,
                        "record_id": record_id
                    })
                    message = f"{vehicle_number} added to waiting queue."
                else:
                    self.slots[free_slot] = {
                        "vehicle_number": vehicle_number,
                        "record_id": record_id
                    }

                    connection = get_connection()
                    try:
                        connection.execute("""
                            UPDATE parking_records
                            SET slot_number = ?, entry_time = ?, status = 'Parked'
                            WHERE id = ?
                        """, (free_slot, self.now(), record_id))
                        connection.commit()
                    finally:
                        connection.close()

                    message = (
                        f"{vehicle_number} parked in slot {free_slot}."
                    )

                    self.semaphore_logs.append(
                        f"{self.now()} - Semaphore permit acquired by {vehicle_number}"
                    )

            else:
                self.waiting_queue.append({
                    "vehicle_number": vehicle_number,
                    "record_id": record_id
                })
                message = f"{vehicle_number} added to FIFO waiting queue."

            self.thread_logs.append(
                f"{self.now()} - Thread completed for {vehicle_number}"
            )

            self.mutex_logs.append(
                f"{self.now()} - Mutex lock released"
            )

            self.log_activity(message)

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
                    SET exit_time = ?, status = 'Exited'
                    WHERE id = ?
                """, (self.now(), vehicle["record_id"]))
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
                        SET slot_number = ?, entry_time = ?, status = 'Parked'
                        WHERE id = ?
                    """, (
                        slot_number,
                        self.now(),
                        next_vehicle["record_id"]
                    ))
                    connection.commit()
                finally:
                    connection.close()

                message = (
                    f"{vehicle_number} exited. "
                    f"{next_vehicle['vehicle_number']} assigned to slot {slot_number}."
                )

                self.semaphore_logs.append(
                    f"{self.now()} - Existing semaphore permit transferred to waiting vehicle"
                )

            else:
                self.slots[slot_number] = None
                self.semaphore.release()

                self.semaphore_logs.append(
                    f"{self.now()} - Semaphore permit released after vehicle exit"
                )

                message = (
                    f"{vehicle_number} exited from slot {slot_number}."
                )

            self.log_activity(message)

            return {
                "success": True,
                "message": message
            }

    def resize_slots(self, new_total):

        with self.lock:

            if new_total < 1:
                return {
                    "success": False,
                    "message": "At least one parking slot is required."
                }

            occupied = sum(
                1 for vehicle in self.slots.values() if vehicle
            )

            if new_total < occupied:
                return {
                    "success": False,
                    "message": "Cannot reduce slots below occupied slots."
                }

            old_slots = self.slots

            self.slots = {
                number: old_slots.get(number)
                for number in range(1, new_total + 1)
            }

            self.total_slots = new_total

            while self.waiting_queue:
                free_slot = next(
                    (
                        number for number, vehicle in self.slots.items()
                        if vehicle is None
                    ),
                    None
                )

                if free_slot is None:
                    break

                next_vehicle = self.waiting_queue.popleft()
                self.slots[free_slot] = next_vehicle

                connection = get_connection()
                try:
                    connection.execute("""
                        UPDATE parking_records
                        SET slot_number = ?, entry_time = ?, status = 'Parked'
                        WHERE id = ?
                    """, (
                        free_slot,
                        self.now(),
                        next_vehicle["record_id"]
                    ))
                    connection.commit()
                finally:
                    connection.close()

            occupied_now = sum(
                1 for vehicle in self.slots.values() if vehicle
            )

            self.semaphore = threading.Semaphore(
                new_total - occupied_now
            )

            connection = get_connection()
            try:
                connection.execute("""
                    UPDATE settings
                    SET setting_value = ?
                    WHERE setting_key = 'total_slots'
                """, (str(new_total),))
                connection.commit()
            finally:
                connection.close()

            message = f"Parking capacity changed to {new_total} slots."

            self.log_activity(message)

            return {
                "success": True,
                "message": message
            }

    def get_state(self):

        with self.lock:

            occupied = sum(
                1 for vehicle in self.slots.values() if vehicle
            )

            slots_data = []

            for number, vehicle in self.slots.items():
                slots_data.append({
                    "slot_number": number,
                    "vehicle_number": (
                        vehicle["vehicle_number"] if vehicle else None
                    ),
                    "status": "Occupied" if vehicle else "Available"
                })

            connection = get_connection()

            try:
                records = connection.execute("""
                    SELECT * FROM parking_records
                    ORDER BY id DESC LIMIT 100
                """).fetchall()

                activities = connection.execute("""
                    SELECT * FROM activity_log
                    ORDER BY id DESC LIMIT 100
                """).fetchall()

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


parking = ParkingSystem()
