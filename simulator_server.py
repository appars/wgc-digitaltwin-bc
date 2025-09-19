# simulator_server.py
"""
Web-service wrapper for the WGC simulator so it can run on Render Free tier
as a Web Service (not a Worker). It exposes /health while a background
thread continuously posts synthetic samples to your backend /ingest-wgc.

Start command on Render:
  gunicorn simulator_server:app --bind 0.0.0.0:$PORT

Environment variables (all optional):
  BACKEND_URL       = https://wgc-digitaltwin-bc-1.onrender.com  (default http://localhost:5050)
  SAMPLE_PERIOD_S   = 0.5      # posting period in seconds (default 0.5). Robust to blank/invalid.
  ENABLE_EXTRAS     = true     # include extra process/health fields (true/false, default true)
  SEED              = <int>    # optional, makes sequence repeatable
"""

import os
import time
import math
import random
import threading
from datetime import datetime, timezone
from typing import Dict, Any

import requests
from flask import Flask, jsonify

# ──────────────────────────────────────────────────────────────────────────────
# Robust env parsing
# ──────────────────────────────────────────────────────────────────────────────
def _get_backend_url() -> str:
    raw = (os.environ.get("BACKEND_URL") or "").strip()
    if not raw:
        raw = "http://localhost:5050"
    return raw.rstrip("/")

def _get_period() -> float:
    raw = (os.environ.get("SAMPLE_PERIOD_S") or "").strip()
    try:
        v = float(raw)
        if v <= 0:
            raise ValueError
        return v
    except Exception:
        return 0.5  # default 2 Hz

def _get_extras_flag() -> bool:
    raw = (os.environ.get("ENABLE_EXTRAS") or "true").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")

def _get_seed():
    raw = (os.environ.get("SEED") or "").strip()
    try:
        return int(raw)
    except Exception:
        return None

BACKEND = _get_backend_url()
INGEST  = f"{BACKEND}/ingest-wgc"
PERIOD  = _get_period()
EXTRAS  = _get_extras_flag()
SEED    = _get_seed()
if SEED is not None:
    random.seed(SEED)

# ──────────────────────────────────────────────────────────────────────────────
# Flask app + state
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

_state = {
    "start_utc": datetime.now(timezone.utc).isoformat(),
    "posted": 0,
    "last_status": None,
    "last_error": None,
    "last_post_utc": None,
}

_stop_evt = threading.Event()

# ──────────────────────────────────────────────────────────────────────────────
# Sample generator (canonical + optional extras)
# ──────────────────────────────────────────────────────────────────────────────
def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def one_sample(t: float, extras: bool = True) -> Dict[str, Any]:
    # Base canonical signals
    u   = 22.0 + 2.0*math.sin(t/15.0) + random.uniform(-0.4, 0.4)        # m/s
    p1  = 2.00e5 + 1200.0*math.sin(t/17.0) + random.uniform(-60, 60)      # Pa
    T1  = 300.0 + 0.6*math.sin(t/23.0) + random.uniform(-0.5, 0.5)        # K
    rho = 1.2 + 0.01*math.sin(t/29.0) + random.uniform(-0.01, 0.01)       # kg/m³
    rpm = 15000 + 80.0*math.sin(t/12.0) + random.uniform(-20, 20)         # rpm
    lvf = clamp(0.01 + 0.003*math.sin(t/21.0) + random.uniform(-0.0015, 0.0015), 0.0, 0.03)

    rec = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "velocity_m_s": round(u, 4),
        "pressure_Pa": round(p1, 3),
        "temperature_K": round(T1, 3),
        "density_kg_m3": round(rho, 4),
        "rpm": int(rpm),
        "liquid_volume_fraction": round(lvf, 6),
    }

    if not extras:
        return rec

    # Extra downstream, controls, and health
    P2_bar = (p1 / 1e5) * (1.20 + 0.04 * math.sin(t / 19.0))               # bar
    T2     = T1 + 2.0 + 0.5 * math.sin(t / 31.0)                           # K
    flow   = rho * u * 0.5 * 0.5                                           # kg/s, crude area=0.25 m² (demo)
    valve  = clamp(55 + 10 * math.sin(t / 28.0) + random.uniform(-2, 2), 0, 100)
    igv    = clamp(50 + 8 * math.sin(t / 33.0) + random.uniform(-2, 2), 0, 100)

    lube   = clamp(2.5 + 0.15 * math.sin(t / 40.0) + random.uniform(-0.05, 0.05), 1.0, 3.5)  # bar
    bearK  = 320.0 + 1.0 * math.sin(t / 37.0) + random.uniform(-0.8, 0.8)                     # K
    seal   = clamp(0.8 + 0.6 * max(0, math.sin(t / 50.0)) + random.uniform(-0.2, 0.2), 0.0, 5.0)  # L/min
    vib_ax = clamp(2.0 + 1.0 * max(0, math.sin(t / 45.0)) + random.uniform(-0.4, 0.4), 0.2, 10.0)
    vib_v  = clamp(2.2 + 1.1 * max(0, math.sin(t / 46.0)) + random.uniform(-0.4, 0.4), 0.2, 10.0)
    vib_h  = clamp(2.1 + 0.9 * max(0, math.sin(t / 47.0)) + random.uniform(-0.4, 0.4), 0.2, 10.0)

    rec.update({
        "P2_bar": round(P2_bar, 5),
        "T2_K": round(T2, 3),
        "mass_flow_kg_s": round(flow, 3),
        "valve_pct": round(valve, 2),
        "igv_pct": round(igv, 2),
        "lube_oil_bar": round(lube, 3),
        "bearing_temp_K": round(bearK, 3),
        "seal_leak_l_min": round(seal, 3),
        "vib_ax_mm_s": round(vib_ax, 3),
        "vib_v_mm_s": round(vib_v, 3),
        "vib_h_mm_s": round(vib_h, 3),
    })
    return rec

# ──────────────────────────────────────────────────────────────────────────────
# Background poster
# ──────────────────────────────────────────────────────────────────────────────
def _pump():
    t0 = time.time()
    s = requests.Session()
    while not _stop_evt.is_set():
        t = time.time() - t0
        payload = one_sample(t, EXTRAS)
        try:
            r = s.post(INGEST, json=payload, timeout=8)
            _state["posted"] = _state.get("posted", 0) + 1
            _state["last_status"] = int(r.status_code)
            _state["last_error"] = None
            _state["last_post_utc"] = datetime.now(timezone.utc).isoformat()
        except requests.RequestException as e:
            _state["last_error"] = str(e)
        # sleep until next tick; respond to stop immediately
        _stop_evt.wait(PERIOD)
    try:
        s.close()
    except Exception:
        pass

def _start_bg():
    th = threading.Thread(target=_pump, daemon=True, name="sim-pump")
    th.start()

# Start immediately on import (gunicorn will import the module then serve)
_start_bg()

# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    try:
        started = datetime.fromisoformat(_state["start_utc"])
        uptime_s = (datetime.now(timezone.utc) - started).total_seconds()
    except Exception:
        uptime_s = None
    return jsonify(
        ok=True,
        ingest=INGEST,
        period_s=PERIOD,
        extras=EXTRAS,
        posted=_state.get("posted", 0),
        last_status=_state.get("last_status"),
        last_error=_state.get("last_error"),
        last_post_utc=_state.get("last_post_utc"),
        start_utc=_state.get("start_utc"),
        uptime_s=uptime_s,
    )

@app.route("/")
def root():
    return jsonify(message="WGC simulator web service. See /health.", health="/health"), 200

# ──────────────────────────────────────────────────────────────────────────────
# Graceful stop on shutdown/redeploy
# ──────────────────────────────────────────────────────────────────────────────
def on_exit():
    _stop_evt.set()

import atexit
atexit.register(on_exit)

# gunicorn discovers `app` automatically

