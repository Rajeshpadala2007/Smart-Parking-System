
// ----------------------------------
// PAGE NAVIGATION
// ----------------------------------

const pageTitles = {
    dashboard: ["Dashboard", "Monitor your parking operations"],
    threads: ["Thread Management", "Monitor vehicle arrival threads"],
    mutex: ["Mutex Management", "Monitor shared resource protection"],
    semaphore: ["Semaphore Management", "Monitor parking capacity permits"],
    waiting: ["Waiting Queue", "Manage vehicles in FIFO order"],
    database: ["Database Records", "View stored parking records"],
    activity: ["Activity Log", "Review system activities"],
    settings: ["Parking Settings", "Configure parking capacity"]
};

document.querySelectorAll(".nav-link").forEach(button => {
    button.addEventListener("click", () => {
        const selectedPage = button.dataset.page;

        document.querySelectorAll(".nav-link").forEach(link => {
            link.classList.remove("active");
        });

        button.classList.add("active");

        document.querySelectorAll(".page").forEach(page => {
            page.classList.remove("active");
        });

        document.getElementById(selectedPage).classList.add("active");

        document.getElementById("pageTitle").textContent =
            pageTitles[selectedPage][0];

        document.getElementById("pageSubtitle").textContent =
            pageTitles[selectedPage][1];

        loadState();
    });
});


// ----------------------------------
// CURRENT DATE
// ----------------------------------

document.getElementById("currentDate").textContent =
    new Date().toLocaleDateString();


// ----------------------------------
// LOAD PARKING DATA
// ----------------------------------

async function loadState() {
    try {
        const response = await fetch("/api/state");

        if (!response.ok) {
            throw new Error("Unable to load parking data.");
        }

        const data = await response.json();

        document.getElementById("totalSlots").textContent =
            data.total_slots;

        document.getElementById("availableSlots").textContent =
            data.available_slots;

        document.getElementById("occupiedSlots").textContent =
            data.occupied_slots;

        document.getElementById("waitingCount").textContent =
            data.waiting_count;

        document.getElementById("settingsCurrentSlots").textContent =
            data.total_slots;


        // PARKING SLOT DISPLAY

        const parkingGrid = document.getElementById("parkingGrid");
        parkingGrid.innerHTML = "";

        data.slots.forEach(slot => {
            const card = document.createElement("div");

            card.className = slot.status === "Occupied"
                ? "slot occupied"
                : "slot available";

            const heading = document.createElement("strong");
            heading.textContent = `Parking Slot ${slot.slot_number}`;

            const vehicle = document.createElement("span");
            vehicle.className = "vehicle-name";
            vehicle.textContent =
                slot.vehicle_number || "No vehicle";

            const status = document.createElement("span");
            status.className = "status-text";
            status.textContent = slot.status;

            card.appendChild(heading);
            card.appendChild(vehicle);
            card.appendChild(status);

            if (slot.status === "Occupied") {
                const exitButton = document.createElement("button");

                exitButton.className = "exit-button";
                exitButton.textContent = "Exit Vehicle";

                exitButton.addEventListener("click", () => {
                    exitVehicle(slot.slot_number);
                });

                card.appendChild(exitButton);
            }

            parkingGrid.appendChild(card);
        });


        // THREAD LOGS

        displayList("threadLogs", data.thread_logs);


        // MUTEX LOGS

        displayList("mutexLogs", data.mutex_logs);


        // SEMAPHORE INFORMATION

        document.getElementById("semaphoreSummary").textContent =
            `${data.available_slots} available permits out of ${data.total_slots} parking slots.`;

        const percentage = data.total_slots > 0
            ? (data.occupied_slots / data.total_slots) * 100
            : 0;

        document.getElementById("capacityBar").style.width =
            `${percentage}%`;

        displayList("semaphoreLogs", data.semaphore_logs);


        // WAITING QUEUE

        displayList("waitingList", data.waiting_queue);


        // DATABASE TABLE

        const databaseTable = document.getElementById("databaseTable");
        databaseTable.innerHTML = "";

        data.database_records.forEach(record => {
            const row = document.createElement("tr");

            const values = [
                record.id,
                record.vehicle_number,
                record.slot_number ?? "-",
                record.arrival_time,
                record.entry_time || "-",
                record.exit_time || "-",
                record.status
            ];

            values.forEach(value => {
                const cell = document.createElement("td");
                cell.textContent = value;
                row.appendChild(cell);
            });

            databaseTable.appendChild(row);
        });


        // ACTIVITY LOG

        const activities = data.activity_logs.map(item =>
            `${item.event_time} - ${item.message}`
        );

        displayList("activityLogs", activities);

    } catch (error) {
        console.error("Dashboard loading error:", error);
    }
}


// ----------------------------------
// DISPLAY LIST
// ----------------------------------

function displayList(elementId, items) {
    const list = document.getElementById(elementId);
    list.innerHTML = "";

    items.forEach(item => {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
    });
}


// ----------------------------------
// VEHICLE ENTRY
// ----------------------------------

document.getElementById("entryForm").addEventListener(
    "submit",
    async function(event) {

        event.preventDefault();

        const vehicleNumber =
            document.getElementById("vehicleNumber").value.trim();

        const message =
            document.getElementById("entryMessage");

        try {
            const response = await fetch("/api/entry", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    vehicle_number: vehicleNumber
                })
            });

            const result = await response.json();

            message.textContent = result.message;
            message.style.color = result.success ? "green" : "red";

            if (result.success) {
                document.getElementById("entryForm").reset();
            }

            setTimeout(loadState, 300);

        } catch (error) {
            message.textContent = "Vehicle entry failed.";
            message.style.color = "red";
        }
    }
);


// ----------------------------------
// VEHICLE EXIT
// ----------------------------------

async function exitVehicle(slotNumber) {

    const confirmed = confirm(
        `Are you sure you want to exit the vehicle in Slot ${slotNumber}?`
    );

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch("/api/exit", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                slot_number: slotNumber
            })
        });

        const result = await response.json();

        alert(result.message);

        loadState();

    } catch (error) {
        alert("Vehicle exit failed.");
    }
}


// ----------------------------------
// SETTINGS - CHANGE SLOT COUNT
// ----------------------------------

document.getElementById("resizeForm").addEventListener(
    "submit",
    async function(event) {

        event.preventDefault();

        const totalSlots =
            document.getElementById("newSlotCount").value;

        const message =
            document.getElementById("resizeMessage");

        try {
            const response = await fetch("/api/resize", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    total_slots: totalSlots
                })
            });

            const result = await response.json();

            message.textContent = result.message;
            message.style.color = result.success ? "green" : "red";

            if (result.success) {
                document.getElementById("resizeForm").reset();
            }

            loadState();

        } catch (error) {
            message.textContent = "Unable to update parking settings.";
            message.style.color = "red";
        }
    }
);


// ----------------------------------
// AUTOMATIC REFRESH EVERY 2 SECONDS
// ----------------------------------

loadState();

setInterval(loadState, 2000);
