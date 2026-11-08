
import os
import uuid
import threading

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    session
)

from database import initialize_database
from parking import ParkingSystem


app = Flask(__name__)

# Secret key
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-development-secret-change-before-deployment"
)

# Session configuration
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
)

app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 365

# Initialize database
initialize_database()

# Store separate parking systems for each browser
parking_systems = {}

# Lock for safe object creation
parking_systems_lock = threading.Lock()


def get_parking():

    # Generate unique browser ID
    if "browser_id" not in session:
        session["browser_id"] = str(uuid.uuid4())
        session.permanent = True

    browser_id = session["browser_id"]

    # Create or restore parking system
    with parking_systems_lock:

        if browser_id not in parking_systems:
            parking_systems[browser_id] = ParkingSystem(browser_id)

        return parking_systems[browser_id]


@app.route("/")
def index():
    get_parking()
    return render_template("index.html", username="Admin")


@app.route("/login", methods=["GET", "POST"])
def login():
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    return redirect(url_for("index"))


@app.route("/api/state")
def api_state():
    return jsonify(get_parking().get_state())


@app.route("/api/entry", methods=["POST"])
def api_entry():

    data = request.get_json(silent=True) or {}
    vehicle_number = data.get("vehicle_number", "")

    if not isinstance(vehicle_number, str):
        return jsonify({
            "success": False,
            "message": "Invalid vehicle number."
        }), 400

    vehicle_number = vehicle_number.strip()

    if not vehicle_number:
        return jsonify({
            "success": False,
            "message": "Enter vehicle number."
        }), 400

    return jsonify(get_parking().add_vehicle(vehicle_number))


@app.route("/api/exit", methods=["POST"])
def api_exit():

    data = request.get_json(silent=True) or {}
    slot_number = data.get("slot_number")

    try:
        slot_number = int(slot_number)
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid parking slot."
        }), 400

    return jsonify(get_parking().exit_vehicle(slot_number))


@app.route("/api/resize", methods=["POST"])
def api_resize():

    data = request.get_json(silent=True) or {}

    try:
        total_slots = int(data.get("total_slots"))
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Enter a valid slot count."
        }), 400

    if total_slots < 1:
        return jsonify({
            "success": False,
            "message": "At least one slot is required."
        }), 400

    return jsonify(get_parking().resize_slots(total_slots))


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False
    )
