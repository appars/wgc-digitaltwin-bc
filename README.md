# WGC Digital Twin — Live Dashboard & BC Recommender

**Wet Gas Compressor (WGC)** real-time dashboard and boundary-condition recommender for CFD solvers (OpenFOAM first).  
Simulator streams telemetry → backend aggregates & recommends BC → Streamlit UI visualizes and lets you **download BC JSON**.

## Key features
- 📡 Live telemetry trends (pressure, temperature, velocity, rpm, density, LVF, flow, valves/IGV, health signals)
- 🔁 Download recent samples (canonical JSON)
- 🧠 Generate **Boundary Conditions** from the shown window (steady-window heuristics, no ML)
- ⬇️ One-click **download BC JSON**
- 🌐 Cloud-ready: Render (backend + simulator), Streamlit Cloud (UI)

---

## 🟢 Current Production (Deployed) Locations


- **Wet Gas Compressor (WGC) - BC Recommender**:  
  **https://wgc-digitaltwin-bc-3zhl7gknvuadgvnd64z8nr.streamlit.app/**
  
- **Backend (Flask)**:  
  **https://wgc-digitaltwin-bc-1.onrender.com**  
  Health: `https://wgc-digitaltwin-bc-1.onrender.com/recent-wgc`

- **Simulator (Render Web Service)**:  
  **https://dashboard.render.com/web/srv-d36erfripnbc739479l0** \
  Health: `https://dashboard.render.com/web/srv-d36erfripnbc739479l0/health`  



**Where to set the UI → backend URL:**  
In Streamlit Cloud, **Settings → Secrets**:
```toml
backend_url = "https://wgc-digitaltwin-bc-1.onrender.com"
```

---

## Repo layout

```
wgc-digitaltwin-bc/
├─ app.py                 # Flask backend (ingest + recommend + recent)
├─ bc_recommender.py      # No-ML BC logic (OpenFOAM-first schema)
├─ streamlit_app.py       # Streamlit UI (talks to backend via HTTP)
├─ simulator/
│   └─ replay.py          # Local CLI simulator (posts to backend)
├─ simulator_server.py    # Web-service simulator (for Render free)
├─ requirements.txt
├─ .python-version        # 3.11.9 (both Render & Streamlit Cloud honor)
└─ runtime.txt            # 3.11.9 (Streamlit Cloud/Heroku honor)
```

---

## 1) How it works (architecture)

```
(simulator) ──► POST /ingest-wgc ─┐
                                  │
                                  ├─> in-memory ring buffer (backend)
                                  │
(UI) ───────► GET /recent-wgc  ───┘
(UI) ───────► POST /recommend-bc  ──► bc_recommender.py ──► BC JSON
```

- **Backend (Flask)**:  
  - `POST /ingest-wgc` — accept single-sample JSON (canonical fields)  
  - `GET /recent-wgc?limit=N` — fetch recent samples  
  - `POST /recommend-bc` — return a **BC JSON** based on samples  
- **UI (Streamlit)**: calls the backend, shows KPIs & charts, lets you **Generate BC** and **Download**.  
- **Simulator**: run locally (`simulator/replay.py`) or as a Render **web service** (`simulator_server.py`).

---

## 2) Local dev & demo

### Create a virtualenv & install deps
```bash
cd wgc-digitaltwin-bc
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start backend
```bash
export PORT=5050
python app.py
```

### Start simulator
```bash
export BACKEND_URL=http://localhost:5050
python simulator/replay.py
```

### Start UI
```bash
export BACKEND_URL=http://localhost:5050
streamlit run streamlit_app.py
```

---

## 3) Cloud deployment

- **Backend**: Render (Flask, gunicorn app:app)  
- **Simulator**: Render (gunicorn simulator_server:app)  
- **UI**: Streamlit Cloud (streamlit_app.py, secret backend_url)

**Render settings (recap)**  
- Backend Health Check Path: `/recent-wgc`  
- Simulator Health Check Path: `/health`  
- Env vars: `PYTHON_VERSION=3.11.9`, `BACKEND_URL`, `SAMPLE_PERIOD_S` (optional), `ENABLE_EXTRAS` (optional)

---

## 4) Canonical sample format

```json
{
  "velocity_m_s": 23.0,
  "pressure_Pa": 200300.0,
  "temperature_K": 300.0,
  "density_kg_m3": 1.20,
  "rpm": 15020,
  "liquid_volume_fraction": 0.012
}
```

---

## 5) Sample Boundary Condition JSON

```json
{
  "gas_model": {
    "assumed": true,
    "composition_mol": {
      "C2H6": 0.05,
      "CH4": 0.9,
      "CO2": 0.03,
      "N2": 0.02
    },
    "eos": "perfectGas"
  },
  "inlet": {
    "multiphase": {
      "lvf": 0.012734
    },
    "total_temperature_K": 300.427,
    "turbulence": {
      "intensity": 0.07,
      "length_scale_m": 0.05
    },
    "type": "velocity_inlet",
    "velocity_m_s": 20.4019
  },
  "meta": {
    "frame": "MRF",
    "schema_version": "1.0",
    "solver": "openfoam",
    "units": "SI"
  },
  "notes": "Data-driven BC; tweak heuristics as needed. Lean NG gas assumed; outlet pressure estimated from inlet.",
  "outlet": {
    "static_pressure_bar": 2.49768,
    "type": "pressure_outlet"
  },
  "rotor": {
    "speed_rpm": 15045
  },
  "validity": {
    "cv": {
      "pressure": 0.003,
      "temperature": 0.0012,
      "velocity": 0.02
    },
    "steady_ok": true,
    "steady_window_samples": 60
  }
}
```

---

## 6) API Endpoints

- `POST /ingest-wgc` → ingest one sample  
- `GET /recent-wgc?limit=N` → get samples  
- `POST /recommend-bc` → generate BC JSON  

---

## 7) Solver usage (OpenFOAM)

- Map `velocity_m_s` → `U` inlet patch  
- Map `static_pressure_bar` → outlet patch `p` (convert bar→Pa)  
- Map `total_temperature_K` → inlet patch `T`  
- `speed_rpm` → convert to rad/s for MRF rotor  

---

## 8) Config

### Env vars
- `BACKEND_URL`  
- `SAMPLE_PERIOD_S` (simulator, default 0.5)  
- `ENABLE_EXTRAS=true` (simulator extras)  

### Health
- Backend: `/recent-wgc`  
- Simulator: `/health`  

---

## 9) For interns

1. Open Streamlit UI → watch KPIs.  
2. Click **Generate Boundary Conditions** → JSON shown.  
3. Download BC JSON.  
4. Use the converter script to create OpenFOAM case `0/` files.  
5. Run solver, verify residuals, pressure ratio, mass flow.

---

## License
Apparsamy Perumal
