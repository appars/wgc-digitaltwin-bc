
from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS

from bc_recommender import recommend_bc

app = Flask(__name__)
CORS(app)

# In-memory ring buffer
RING_MAX = 10000
ring = deque(maxlen=RING_MAX)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _normalize_sample(s: Dict[str, Any]) -> Dict[str, Any]:
    s = dict(s)
    # ensure canonical keys exist or are numeric if present
    for k in ["velocity_m_s", "pressure_Pa", "temperature_K", "density_kg_m3", "rpm", "liquid_volume_fraction"]:
        if k in s:
            try:
                s[k] = float(s[k])
            except Exception:
                pass
    if "rpm" in s:
        try:
            s["rpm"] = int(s["rpm"])
        except Exception:
            pass
    # stamp time if missing
    if "timestamp_utc" not in s:
        s["timestamp_utc"] = _now_iso()
    return s

@app.route("/ingest-wgc", methods=["POST"])
def ingest():
    """
    Accepts a JSON object or an array of objects with canonical fields:
    velocity_m_s, pressure_Pa, temperature_K, density_kg_m3, rpm, liquid_volume_fraction
    """
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({"ok": False, "error": f"invalid json: {e}"}), 400

    if isinstance(payload, dict):
        samples = [payload]
    elif isinstance(payload, list):
        samples = payload
    else:
        return jsonify({"ok": False, "error": "payload must be object or array of objects"}), 400

    added = 0
    for s in samples:
        ring.append(_normalize_sample(s))
        added += 1
    return jsonify({"ok": True, "added": added, "size": len(ring)})

@app.route("/recent-wgc", methods=["GET"])
def recent():
    try:
        limit = int(request.args.get("limit", 200))
        limit = max(1, min(limit, RING_MAX))
    except Exception:
        limit = 200
    # return the most recent 'limit' samples
    data = list(ring)[-limit:]
    return jsonify({"ok": True, "samples": data, "count": len(data)})

@app.route("/recommend-bc", methods=["POST"])
def recommend():
    """
    Expects list[dict] canonical samples. Returns {'bc': {...}}.
    """
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({"ok": False, "error": f"invalid json: {e}"}), 400

    if not isinstance(payload, list) or not payload:
        return jsonify({"ok": False, "error": "expected a non-empty JSON array of samples"}), 400

    try:
        bc = recommend_bc(payload)
        return jsonify({"ok": True, "bc": bc})
    except Exception as e:
        return jsonify({"ok": False, "error": f"recommender failed: {e}"}), 500

if __name__ == "__main__":
    # default port 5050 for local dev
    import os
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="0.0.0.0", port=port)
