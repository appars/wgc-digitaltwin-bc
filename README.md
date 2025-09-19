# WGC Digital Twin — Live Dashboard & BC Recommender

**Wet Gas Compressor (WGC)** real-time dashboard and **no-ML** boundary-condition recommender for CFD solvers (OpenFOAM first).  
Simulator streams telemetry → backend aggregates & recommends BC → Streamlit UI visualizes and lets you **download BC JSON**.

## Key features
- 📡 Live telemetry trends (pressure, temperature, velocity, rpm, density, LVF, flow, valves/IGV, health signals)
- 🔁 Download recent samples (canonical JSON)
- 🧠 Generate **Boundary Conditions** from the shown window (steady-window heuristics, no ML)
- ⬇️ One-click **download BC JSON**
- 🌐 Cloud-ready: Render (backend + simulator), Streamlit Cloud (UI)

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

## 5) API Endpoints

- `POST /ingest-wgc` → ingest one sample  
- `GET /recent-wgc?limit=N` → get samples  
- `POST /recommend-bc` → generate BC JSON  

---

## 6) Solver usage (OpenFOAM)

- Map `velocity_m_s` → `U` inlet patch  
- Map `static_pressure_bar` → outlet patch `p` (convert bar→Pa)  
- Map `total_temperature_K` → inlet patch `T`  
- `speed_rpm` → convert to rad/s for MRF rotor  

---

## 7) Config

### Env vars
- `BACKEND_URL`  
- `SAMPLE_PERIOD_S` (simulator, default 0.5)  
- `ENABLE_EXTRAS=true` (simulator extras)  

### Health
- Backend: `/recent-wgc`  
- Simulator: `/health`  

---

## 8) For interns

1. Open Streamlit UI → watch KPIs.  
2. Click **Generate Boundary Conditions** → JSON shown.  
3. Download BC JSON.  
4. Use converter script to create OpenFOAM case `0/` files.  
5. Run solver, verify residuals, pressure ratio, mass flow.

---

## License
MIT (adjust if needed)
