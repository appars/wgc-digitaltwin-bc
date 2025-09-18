
"""
Simple simulator that posts synthetic samples to the backend /ingest-wgc.
Usage:
  export BACKEND_URL=http://localhost:5050
  python simulator/replay.py
"""
import os, time, math, random, json
from datetime import datetime, timezone
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:5050").rstrip("/")
INGEST = f"{BACKEND}/ingest-wgc"

def one_sample(t: float) -> dict:
    base_u = 22.0 + 2.0*math.sin(t/15.0)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "velocity_m_s": round(base_u + random.uniform(-0.4, 0.4), 4),
        "pressure_Pa": round(2.0e5 + 1200.0*math.sin(t/17.0) + random.uniform(-50, 50), 3),
        "temperature_K": round(300.0 + random.uniform(-0.5, 0.5), 3),
        "density_kg_m3": round(1.2 + random.uniform(-0.01, 0.01), 4),
        "rpm": int(15000 + 60.0*math.sin(t/12.0) + random.uniform(-20, 20)),
        "liquid_volume_fraction": round(max(0.0, 0.01 + random.uniform(-0.002, 0.002)), 6),
    }

def main():
    print(f"Posting to {INGEST} ... Ctrl+C to stop.")
    t0 = time.time()
    while True:
        t = time.time() - t0
        payload = one_sample(t)
        try:
            r = requests.post(INGEST, json=payload, timeout=5)
            print(f"{datetime.now().isoformat()} status={r.status_code}")
        except Exception as e:
            print("post error:", e)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
