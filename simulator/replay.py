# simulator/replay.py
"""
Synthetic WGC telemetry poster to /ingest-wgc with extra process/health fields.
Usage:
  export BACKEND_URL=http://localhost:5050
  python simulator/replay.py
"""
import os, time, math, random
from datetime import datetime, timezone
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:5050").rstrip("/")
INGEST = f"{BACKEND}/ingest-wgc"

def clamp(x, lo, hi): return max(lo, min(hi, x))

def one_sample(t: float) -> dict:
    # base waves
    u   = 22.0 + 2.0*math.sin(t/15.0) + random.uniform(-0.4, 0.4)      # m/s
    p1  = 2.00e5 + 1200.0*math.sin(t/17.0) + random.uniform(-60, 60)    # Pa
    T1  = 300.0 + 0.6*math.sin(t/23.0) + random.uniform(-0.5, 0.5)      # K
    rho = 1.2 + 0.01*math.sin(t/29.0) + random.uniform(-0.01, 0.01)     # kg/m3
    rpm = 15000 + 80.0*math.sin(t/12.0) + random.uniform(-20, 20)       # rpm
    lvf = clamp(0.01 + 0.003*math.sin(t/21.0) + random.uniform(-0.0015, 0.0015), 0.0, 0.03)

    # downstream & controls
    P2_bar = (p1/1e5) * (1.20 + 0.04*math.sin(t/19.0))                   # bar, ~20% higher than inlet
    T2     = T1 + 2.0 + 0.5*math.sin(t/31.0)                              # K, slightly warmer
    flow   = rho * u * 0.5 * 0.5                                         # kg/s, crude area=0.25 m^2 (demo)
    valve  = clamp(55 + 10*math.sin(t/28.0) + random.uniform(-2, 2), 0, 100)
    igv    = clamp(50 + 8*math.sin(t/33.0) + random.uniform(-2, 2), 0, 100)

    # health
    lube   = clamp(2.5 + 0.15*math.sin(t/40.0) + random.uniform(-0.05, 0.05), 1.0, 3.5)  # bar
    bearK  = 320.0 + 1.0*math.sin(t/37.0) + random.uniform(-0.8, 0.8)                     # K
    seal   = clamp(0.8 + 0.6*max(0, math.sin(t/50.0)) + random.uniform(-0.2, 0.2), 0.0, 5.0) # L/min
    vib_ax = clamp(2.0 + 1.0*max(0, math.sin(t/45.0)) + random.uniform(-0.4, 0.4), 0.2, 10.0)
    vib_v  = clamp(2.2 + 1.1*max(0, math.sin(t/46.0)) + random.uniform(-0.4, 0.4), 0.2, 10.0)
    vib_h  = clamp(2.1 + 0.9*max(0, math.sin(t/47.0)) + random.uniform(-0.4, 0.4), 0.2, 10.0)

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        # canonical fields
        "velocity_m_s": round(u, 4),
        "pressure_Pa": round(p1, 3),
        "temperature_K": round(T1, 3),
        "density_kg_m3": round(rho, 4),
        "rpm": int(rpm),
        "liquid_volume_fraction": round(lvf, 6),
        # added process/control
        "P2_bar": round(P2_bar, 5),
        "T2_K": round(T2, 3),
        "mass_flow_kg_s": round(flow, 3),
        "valve_pct": round(valve, 2),
        "igv_pct": round(igv, 2),
        # health
        "lube_oil_bar": round(lube, 3),
        "bearing_temp_K": round(bearK, 3),
        "seal_leak_l_min": round(seal, 3),
        "vib_ax_mm_s": round(vib_ax, 3),
        "vib_v_mm_s": round(vib_v, 3),
        "vib_h_mm_s": round(vib_h, 3),
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

