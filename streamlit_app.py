
import os, json, time, math, random
from datetime import datetime

import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="WGC Digital Twin — Live Dashboard & BC Recommender", layout="wide")
st.title("Wet Gas Compressor — Live Dashboard & BC Recommender (No-ML)")

def resolve_backend_url() -> str:
    url = os.environ.get("BACKEND_URL")
    if not url:
        try:
            url = st.secrets.get("backend_url")
        except Exception:
            url = None
    return (url or "http://localhost:5050").rstrip("/")

BACKEND_URL   = resolve_backend_url()
RECOMMEND_URL = f"{BACKEND_URL}/recommend-bc"
RECENT_URL    = f"{BACKEND_URL}/recent-wgc"

# Session state
for k, v in {
    "bc_live": None,
    "rev_live": 0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Helpers
def get_backend_health() -> str:
    try:
        r = requests.get(RECENT_URL, params={"limit": 1}, timeout=5)
        r.raise_for_status()
        return "OK"
    except Exception as e:
        return f"DOWN: {e}"

def fetch_recent(limit=200) -> pd.DataFrame:
    try:
        r = requests.get(RECENT_URL, params={"limit": limit}, timeout=10)
        r.raise_for_status()
        data = r.json().get("samples", [])
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def post_recommend(payload):
    try:
        r = requests.post(RECOMMEND_URL, json=payload, timeout=25)
        try:
            data = r.json()
        except Exception:
            data = r.text
        return (True, data) if r.ok else (False, data)
    except Exception as e:
        return False, str(e)

def add_trend_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "pressure_Pa" in df.columns:
        df["pressure_bar"] = pd.to_numeric(df["pressure_Pa"], errors="coerce") / 1e5
    if "temperature_K" in df.columns:
        df["temperature_C"] = pd.to_numeric(df["temperature_K"], errors="coerce") - 273.15
    if "rpm" in df.columns:
        df["rpm_k"] = pd.to_numeric(df["rpm"], errors="coerce") / 1000.0
    return df

FRIENDLY_LABELS = {
    "pressure_bar":  "pressure (bar)",
    "temperature_C": "temperature (°C)",
    "rpm_k":         "rpm (kRPM)",
    "density_kg_m3": "density (kg/m³)",
    "velocity_m_s":  "velocity (m/s)",
    "liquid_volume_fraction": "LVF (–)",
}

CANONICAL_FIELDS = [
    "velocity_m_s", "pressure_Pa", "temperature_K",
    "density_kg_m3", "rpm", "liquid_volume_fraction",
]

def normalize_bc_response(res):
    try:
        parsed = json.loads(res) if isinstance(res, str) else res
    except Exception:
        return None
    if isinstance(parsed, dict) and "bc" in parsed and isinstance(parsed["bc"], dict):
        return parsed["bc"]
    if isinstance(parsed, dict):
        return parsed
    return None

# Sidebar
with st.sidebar:
    st.subheader("Backend")
    st.text_input("Backend URL", BACKEND_URL, disabled=True)
    health = get_backend_health()
    (st.success if health == "OK" else st.error)(f"Backend: {health if health!='OK' else 'OK'}")
    st.caption("Endpoints: POST /recommend-bc, GET /recent-wgc")
    st.divider()
    st.subheader("Controls")
    limit = st.number_input("Rows to pull", 50, 5000, 200, 50)
    refresh_s = st.number_input("Auto refresh (s)", 1, 30, 3, 1)
    auto_refresh = st.toggle("Auto refresh", True)

# Live section
st.markdown("### 📡 Live Telemetry")
kpi_ph   = st.empty()
trend_ph = st.empty()
dl_ph    = st.empty()
bc_ph    = st.empty()

def to_canonical_payload(df: pd.DataFrame):
    base_cols = [c for c in CANONICAL_FIELDS if c in df.columns]
    if not base_cols:
        if "pressure_bar" in df.columns: df["pressure_Pa"] = df["pressure_bar"]*1e5
        if "temperature_C" in df.columns: df["temperature_K"] = df["temperature_C"]+273.15
        if "rpm_k" in df.columns: df["rpm"] = df["rpm_k"]*1000.0
        base_cols = [c for c in CANONICAL_FIELDS if c in df.columns]
    payload = df[base_cols].to_dict(orient="records") if base_cols else []
    return payload

def render_live_once():
    df = fetch_recent(int(limit))
    if df.empty:
        kpi_ph.empty(); trend_ph.empty(); dl_ph.empty()
        st.info("No samples yet. Start the simulator (see README).")
        return None, None

    df = add_trend_columns(df)

    latest = df.iloc[-1].to_dict()
    with kpi_ph.container():
        st.markdown("#### Latest KPIs")
        kpis = [c for c in ["pressure_bar","temperature_C","density_kg_m3","velocity_m_s","rpm_k","liquid_volume_fraction"] if c in df.columns]
        cols = st.columns(len(kpis)) if kpis else [st.container()]
        for i, c in enumerate(kpis):
            label = FRIENDLY_LABELS.get(c, c)
            val = latest.get(c, None)
            if val is None and c == "pressure_bar" and "pressure_Pa" in latest: val = float(latest["pressure_Pa"])/1e5
            if val is None and c == "temperature_C" and "temperature_K" in latest: val = float(latest["temperature_K"])-273.15
            if val is None and c == "rpm_k" and "rpm" in latest: val = float(latest["rpm"])/1000.0
            if val is None: val = "—"
            if isinstance(val, (int,float)):
                if c=="pressure_bar": val = f"{val:.3f}"
                elif c=="temperature_C": val = f"{val:.2f}"
                elif c=="rpm_k": val = f"{val:.2f}"
                elif c=="velocity_m_s": val = f"{val:.3f}"
                elif c=="density_kg_m3": val = f"{val:.3f}"
                elif c=="liquid_volume_fraction": val = f"{val:.4f}"
            cols[i].metric(label, val)

    trend_cols = [c for c in ["pressure_bar","temperature_C","velocity_m_s","rpm_k","liquid_volume_fraction"] if c in df.columns]
    if trend_cols:
        plot_df = df[trend_cols].copy().rename(columns={
            "pressure_bar":"Pressure (bar)",
            "temperature_C":"Temperature (°C)",
            "velocity_m_s":"Velocity (m/s)",
            "rpm_k":"RPM (×1000)",
            "liquid_volume_fraction":"LVF (–)",
        })
        if "timestamp_utc" in df.columns:
            try: plot_df.index = pd.to_datetime(df["timestamp_utc"], errors="coerce")
            except Exception: pass
        with trend_ph.container():
            st.markdown("#### Trends (combined)")
            st.line_chart(plot_df, height=240, use_container_width=True)
    else:
        trend_ph.info("Not enough fields for trends.")

    # Download recent as canonical JSON
    payload = to_canonical_payload(df.tail(int(limit)))
    dl_ph.empty()
    dl_ph.download_button(
        "⬇️ Download recent samples (JSON)",
        data=json.dumps(payload, indent=2),
        file_name=f"recent_samples_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        use_container_width=True,
        key=f"dl_recent_{datetime.utcnow().strftime('%H%M%S%f')}"
    )

    return df.tail(int(limit)), payload

current_df, current_payload = render_live_once()

if st.button("Generate Boundary Conditions from shown samples", type="primary"):
    if not current_payload:
        bc_ph.warning("No data available to generate BC.")
    else:
        with st.spinner("Requesting recommendation..."):
            ok, res = post_recommend(current_payload)
        bc = normalize_bc_response(res)
        if not ok or bc is None:
            bc_ph.error(f"Backend error or unexpected response:\n{res}")
        else:
            st.session_state.bc_live = bc

if st.session_state.bc_live:
    bc_ph.empty()
    st.session_state["rev_live"] += 1
    rev = st.session_state["rev_live"]
    with bc_ph.container():
        st.subheader("BC Recommendation (JSON)")
        st.json(st.session_state.bc_live)
        st.download_button(
            "⬇️ Download BC JSON",
            data=json.dumps(st.session_state.bc_live, indent=2),
            file_name=f"bc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
            key=f"dl_bc_{rev}",
        )

if auto_refresh:
    for _ in range(max(1, int(60 / max(int(refresh_s), 1)))):
        time.sleep(int(refresh_s))
        current_df, current_payload = render_live_once()
        if st.session_state.bc_live:
            bc_ph.empty()
            st.session_state["rev_live"] += 1
            rev = st.session_state["rev_live"]
            with bc_ph.container():
                st.subheader("BC Recommendation (JSON)")
                st.json(st.session_state.bc_live)
                st.download_button(
                    "⬇️ Download BC JSON",
                    data=json.dumps(st.session_state.bc_live, indent=2),
                    file_name=f"bc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True,
                    key=f"dl_bc_{rev}",
                )

st.markdown("---")
st.caption(f"Backend: {BACKEND_URL} • Endpoints: POST /recommend-bc, GET /recent-wgc")
