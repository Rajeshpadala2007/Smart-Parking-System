
from flask import Flask, render_template, request, jsonify, redirect, url_for

from database import initialize_database

initialize_database()

from parking import parking

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", username="Admin")


@app.route("/login", methods=["GET", "POST"])
def login():
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    return redirect(url_for("index"))


@app.route("/api/state")
def api_state():
    return jsonify(parking.get_state())


@app.route("/api/entry", methods=["POST"])
def api_entry():
    data = request.get_json(silent=True) or {}
    vehicle_number = data.get("vehicle_number", "").strip()

    if not vehicle_number:
        return jsonify({
            "success": False,
            "message": "Enter vehicle number."
        }), 400

    return jsonify(parking.add_vehicle(vehicle_number))


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

    return jsonify(parking.exit_vehicle(slot_number))


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

    return jsonify(parking.resize_slots(total_slots))


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False
    )
