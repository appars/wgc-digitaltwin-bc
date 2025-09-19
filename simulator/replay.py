# simulator/replay.py (graceful shutdown)
import os, time, math, random, signal, sys
from datetime import datetime, timezone
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:5050").rstrip("/")
INGEST = f"{BACKEND}/ingest-wgc"

stop = False
def _stop(signum, frame):
    global stop
    stop = True

# Handle Ctrl+C and SIGTERM cleanly
signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

def clamp(x, lo, hi): return max(lo, min(hi, x))

def one_sample(t: float) -> dict:
    u   = 22.0 + 2.0*math.sin(t/15.0) + random.uniform(-0.4, 0.4)
    p1  = 2.00e5 + 1200.0*math.sin(t/17.0) + random.uniform(-60, 60)
    T1  = 300.0 + 0.6*math.sin(t/23.0) + random.uniform(-0.5, 0.5)
    rho = 1.2 + 0.01*math.sin(t/29.0) + random.uniform(-0.01, 0.01)
    rpm = 15000 + 80.0*math.sin(t/12.0) + random.uniform(-20, 20)
    lvf = clamp(0.01 + 0.003*math.sin(t/21.0) + random.uniform(-0.0015, 0.0015), 0.0, 0.03)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "velocity_m_s": round(u, 4),
        "pressure_Pa": round(p1, 3),
        "temperature_K": round(T1, 3),
        "density_kg_m3": round(rho, 4),
        "rpm": int(rpm),
        "liquid_volume_fraction": round(lvf, 6),
    }

def main():
    print(f"Posting to {INGEST} ... Ctrl+C to stop.")
    t0 = time.time()
    s = requests.Session()
    try:
        while not stop:
            t = time.time() - t0
            payload = one_sample(t)
            try:
                r = s.post(INGEST, json=payload, timeout=5)
                print(f"{datetime.now().isoformat()} status={r.status_code}")
            except requests.exceptions.RequestException as e:
                # transient network error; log and keep going
                print("post error:", e)
                time.sleep(1.0)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nSimulator stopped by user. Bye 👋")
        try: s.close()
        except Exception: pass
        sys.exit(0)

if __name__ == "__main__":
    main()

