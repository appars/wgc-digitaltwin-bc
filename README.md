
# WGC Digital Twin — No-ML BC Recommender (OpenFOAM)

Single-page Streamlit UI + Flask backend. No-ML physics/heuristics generate Boundary Conditions JSON. Includes a simple simulator.

## Run locally

### 1) Backend
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PORT=5050
python app.py
```

### 2) Simulator (optional)
```bash
export BACKEND_URL=http://localhost:5050
python simulator/replay.py
```

### 3) UI
```bash
export BACKEND_URL=http://localhost:5050
streamlit run streamlit_app.py
```

## Endpoints
- `POST /ingest-wgc` — ingest one or many samples (canonical fields).
- `GET  /recent-wgc?limit=200` — fetch recent samples.
- `POST /recommend-bc` — returns `{"bc": {...}}` (no-ML heuristic).

## Canonical sample fields (SI)
- `velocity_m_s`, `pressure_Pa`, `temperature_K`, `density_kg_m3`, `rpm`, `liquid_volume_fraction`

## What the BC includes
- OpenFOAM-friendly, solver-agnostic JSON with inlet (velocity/total T), outlet static pressure, rotor speed, turbulence (TI/ℓ), LVF, validity (steady check), and clear notes.
