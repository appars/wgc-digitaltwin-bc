#!/usr/bin/env python3
"""
WGC telemetry simulator

Modes:
  synthetic        -> generate live samples at a fixed rate
  replay --file F  -> replay CSV or JSON-lines file; optional --respect-time

CSV headers (recommended):
  timestamp_utc,velocity_m_s,pressure_Pa,temperature_K,density_kg_m3,liquid_volume_fraction,rpm
JSON lines: one JSON object per line with the same keys as above.
"""

import os, time, math, json, random, argparse, csv
from datetime import datetime, timezone
import requests
from pathlib import Path

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def gen_sample(t: float):
    base_u = 22.0 + 2.0 * math.sin(t / 15.0)
    u = base_u + random.uniform(-0.4, 0.4)
    p = 2e5 + 1200.0 * math.sin(t / 17.0) + random.uniform(-50, 50)
    T = 300.0 + random.uniform(-0.4, 0.4)
    rho = 1.2 + random.uniform(-0.01, 0.01)
    lvf = max(0.0, 0.01 + random.uniform(-0.002, 0.002))
    rpm = int(15000 + 60.0 * math.sin(t / 12.0) + random.uniform(-20, 20))
    return {
        "timestamp_utc": now_iso(),
        "velocity_m_s": round(u, 4),
        "pressure_Pa": round(p, 3),
        "temperature_K": round(T, 3),
        "density_kg_m3": round(rho, 4),
        "liquid_volume_fraction": round(lvf, 6),
        "rpm": rpm,
    }

def post_samples(backend_url: str, samples):
    url = backend_url.rstrip("/") + "/ingest-wgc"
    try:
        resp = requests.post(url, json=samples, timeout=3.0)
        resp.raise_for_status()
        return True, resp.json()
    except Exception as e:
        return False, str(e)

def parse_iso(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()

def load_replay_file(path: Path):
    """Return list[dict] samples from CSV or JSON lines."""
    if not path.exists():
        raise FileNotFoundError(path)
    samples = []
    ext = path.suffix.lower()
    if ext in (".jl", ".jsonl", ".ndjson"):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    samples.append(json.loads(line))
    elif ext == ".csv":
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                s = {}
                for k, v in row.items():
                    if v is None or v == "":
                        continue
                    key = k.strip()
                    if "timestamp" in key.lower():
                        s["timestamp_utc"] = v
                        continue
                    # try number
                    try:
                        s[key] = float(v) if "." in v else int(v)
                    except Exception:
                        s[key] = v
                # ensure timestamp
                s.setdefault("timestamp_utc", now_iso())
                samples.append(s)
    else:
        # try JSON array
        with open(path, "r") as f:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON must be an array of samples.")
            samples = data
    return samples

def run_synthetic(backend, rate, batch_size, quiet):
    period = 1.0 / max(rate, 0.1)
    t0 = time.time()
    i = 0
    print(f"[SIM] synthetic -> {backend} @ {rate} Hz (batch={batch_size})")
    try:
        while True:
            t = time.time() - t0
            payload = [gen_sample(t + 0.01*k) for k in range(batch_size)]
            ok, info = post_samples(backend, payload)
            if not quiet:
                status = "OK" if ok else f"ERR: {info}"
                print(f"[SIM] #{i:06d} {status} u={payload[0]['velocity_m_s']} p={payload[0]['pressure_Pa']}")
            i += 1
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n[SIM] stopped.")

def run_replay(backend, file_path, rate, respect_time, loop, batch_size, quiet):
    p = Path(file_path)
    samples = load_replay_file(p)
    print(f"[SIM] replay {p} -> {backend} (N={len(samples)}, respect_time={respect_time}, rate={rate} Hz, batch={batch_size}, loop={loop})")
    idx = 0
    last_ts = None
    try:
        while True:
            # batch
            batch = []
            for _ in range(batch_size):
                batch.append(samples[idx % len(samples)])
                idx += 1
            # pacing
            if respect_time:
                ts_s = parse_iso(batch[0].get("timestamp_utc", now_iso()))
                if last_ts is None:
                    wait = 0.0
                else:
                    wait = max(0.0, ts_s - last_ts)
                last_ts = ts_s
                if wait > 0:
                    time.sleep(wait)
            else:
                period = 1.0 / max(rate, 0.1)
                time.sleep(period)
            ok, info = post_samples(backend, batch)
            if not quiet:
                status = "OK" if ok else f"ERR: {info}"
                print(f"[SIM] replay idx={idx-len(batch)}..{idx-1} {status}")
            if idx >= len(samples) and not loop:
                print("[SIM] reached end (loop=False).")
                break
    except KeyboardInterrupt:
        print("\n[SIM] stopped.")

def main():
    ap = argparse.ArgumentParser(description="WGC simulator (synthetic or replay)")
    sub = ap.add_subparsers(dest="mode", required=False)

    # common defaults
    default_backend = os.environ.get("BACKEND_URL", "http://backend:5000")

    p_syn = sub.add_parser("synthetic")
    p_syn.add_argument("--backend", "-b", default=default_backend)
    p_syn.add_argument("--rate", "-r", type=float, default=2.0)
    p_syn.add_argument("--batch-size", type=int, default=1)
    p_syn.add_argument("--quiet", action="store_true")

    p_rep = sub.add_parser("replay")
    p_rep.add_argument("--backend", "-b", default=default_backend)
    p_rep.add_argument("--file", "-f", required=True)
    p_rep.add_argument("--rate", "-r", type=float, default=5.0, help="used when not respecting time")
    p_rep.add_argument("--respect-time", action="store_true", help="sleep using timestamp deltas")
    p_rep.add_argument("--loop", action="store_true")
    p_rep.add_argument("--batch-size", type=int, default=1)
    p_rep.add_argument("--quiet", action="store_true")

    args = ap.parse_args()
    if args.mode == "replay":
        run_replay(args.backend, args.file, args.rate, args.respect_time, args.loop, args.batch_size, args.quiet)
    else:
        # default to synthetic if no subcommand
        run_synthetic(
            getattr(args, "backend", default_backend),
            getattr(args, "rate", 2.0),
            getattr(args, "batch_size", 1),
            getattr(args, "quiet", False),
        )

if __name__ == "__main__":
    main()

