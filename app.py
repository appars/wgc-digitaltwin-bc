# app.py
import os
import json
import time
from collections import deque
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# -----------------------
# Paths / constants
# -----------------------
APP_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(APP_DIR, "static")
HIST_DIR = os.path.join(STATIC_DIR, "bc_history")
os.makedirs(HIST_DIR, exist_ok=True)

# Ring buffer for recent telemetry
RING_LIMIT = int(os.environ.get("RING_LIMIT", "5000"))
RING = deque(maxlen=RING_LIMIT)

# -----------------------
# App init
# -----------------------
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app)


# -----------------------
# Routes
# -----------------------
@app.route("/ingest-wgc", methods=["POST"])
def ingest_wgc():
    """
    Accepts a single sample dict OR a list of sample dicts.
    Stores them in an in-memory ring buffer for quick visualization.
    """
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({"error": f"invalid JSON: {e}"}), 400

    if isinstance(payload, dict):
        samples = [payload]
    elif isinstance(payload, list):
        samples = payload
    else:
        return jsonify({"error": "payload must be a dict or list[dict]"}), 400

    for s in samples:
        RING.append(s)

    return jsonify({"status": "ok", "received": len(samples), "buffer_len": len(RING)}), 200


@app.route("/recent-wgc", methods=["GET"])
def recent_wgc():
    """
    Returns the last N samples for UI visualization.
    GET /recent-wgc?limit=200
    """
    try:
        limit = int(request.args.get("limit", 200))
    except Exception:
        limit = 200
    limit = max(1, min(limit, RING_LIMIT))
    data = list(RING)[-limit:]
    return jsonify({"count": len(data), "samples": data}), 200


@app.route("/recommend-bc", methods=["POST"])
def recommend_bc_route():
    """
    Accepts a JSON array of samples and returns a BC recommendation.
    Also saves a timestamped JSON under static/bc_history/ and returns its URL.
    """
    from bc_recommender import recommend_bc  # local module

    payload = request.get_json(silent=True) or []
    if not isinstance(payload, list):
        return jsonify({"error": "payload must be a JSON array (list) of sample objects"}), 400

    # Compute BC recommendation (your function can be simple or advanced)
    bc = recommend_bc(payload)

    # Save BC JSON to history with timestamped filename
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"bc_{ts}.json"
    fpath = os.path.join(HIST_DIR, fname)
    with open(fpath, "w") as f:
        json.dump(bc, f, indent=2)

    # Return both the BC object and a relative download URL
    return jsonify({
        "bc": bc,
        "download": f"/static/bc_history/{fname}"
    }), 200


@app.route("/static/bc_history/<path:filename>")
def download_bc(filename: str):
    """
    Direct download for a previously saved BC JSON.
    """
    return send_from_directory(HIST_DIR, filename, as_attachment=True)


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok", "buffer_len": len(RING)}), 200


# -----------------------
# Main
# -----------------------
if __name__ == "__main__":
    # Default to 5050 since you're using it; change via env PORT if you like
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)

