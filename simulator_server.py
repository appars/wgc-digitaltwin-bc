# simulator_server.py
import os, time, threading, math, random
from datetime import datetime, timezone
import requests
from flask import Flask, jsonify

BACKEND = os.environ.get("BACKEND_URL", "https://wgc-digitaltwin-bc-1.onrender.com").rstrip("/")
INGEST = f"{BACKEND}/ingest-wgc"
SAMPLE_PERIOD_S = float(os.environ.get("SAMPLE_PERIOD_S", "0.5"))

app = Flask(__name__)
running = True

def clamp(x, lo, hi): return max(lo, min(hi, x))

def one_sample(t: float) -> dict:
    u   = 22.0 + 2.0*math.sin(t/15.0) + random.uniform(-0.4, 0.4)
    p1  = 2.00e5 + 1200.0*math.sin(t/17.0) + random.uniform(-60, 60)
    T1  = 300.0 + 0.6*math.sin(t/23.0) + random.uniform(-0.5, 0.5)
    rho = 1.2 + 0.01*math.sin(t/29.0) + random.uniform(-0.01, 0.01)
    rpm = int(15000 + 80.0*math.sin(t/12.0) + random.uniform(-20, 20))
    lvf = clamp(0.01 + 0.003*math.sin(t/21.0) + random.uniform(-0.0015, 0.0015), 0.0, 0.03)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "velocity_m_s": round(u,4),
        "pressure_Pa": round(p1,3),
        "temperature_K": round(T1,3),
        "density_kg_m3": round(rho,4),
        "rpm": rpm,
        "liquid_volume_fraction": round(lvf,6),
    }

def pump():
    t0 = time.time()
    s = requests.Session()
    while running:
        t = time.time() - t0
        payload = one_sample(t)
        try:
            s.post(INGEST, json=payload, timeout=5)
        except requests.RequestException:
            pass
        time.sleep(SAMPLE_PERIOD_S)

@app.route("/health")
def health():
    return jsonify(ok=True, ingest=INGEST, period_s=SAMPLE_PERIOD_S)

def start_bg():
    th = threading.Thread(target=pump, daemon=True)
    th.start()

start_bg()  # start on import

