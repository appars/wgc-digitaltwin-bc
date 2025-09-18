# streamlit_app.py
import os, json, time
from datetime import datetime

import requests
import pandas as pd
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# Page setup
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="WGC Digital Twin — Live Dashboard & BC Recommender", layout="wide")
st.title("Wet Gas Compressor — Live Dashboard & BC Recommender")

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

# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
for k, v in {"bc_live": None, "rev_live": 0}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
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

def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df
    df = df.copy()
    # Base derived
    if "pressure_Pa" in df.columns:
        df["pressure_bar"] = pd.to_numeric(df["pressure_Pa"], errors="coerce") / 1e5
    if "temperature_K" in df.columns:
        df["temperature_C"] = pd.to_numeric(df["temperature_K"], errors="coerce") - 273.15
    if "rpm" in df.columns:
        df["rpm_k"] = pd.to_numeric(df["rpm"], errors="coerce") / 1000.0
    # Optional downstream/health derived
    if "T2_K" in df.columns:
        df["T2_C"] = pd.to_numeric(df["T2_K"], errors="coerce") - 273.15
    if "bearing_temp_K" in df.columns:
        df["bearing_temp_C"] = pd.to_numeric(df["bearing_temp_K"], errors="coerce") - 273.15
    if "liquid_volume_fraction" in df.columns:
        df["LVF_pct"] = pd.to_numeric(df["liquid_volume_fraction"], errors="coerce") * 100.0
    return df

FRIENDLY = {
    "pressure_bar":  "pressure (bar)",
    "temperature_C": "temperature (°C)",
    "velocity_m_s":  "velocity (m/s)",
    "rpm_k":         "rpm (kRPM)",
    "density_kg_m3": "density (kg/m³)",
    "liquid_volume_fraction": "LVF (–)",
    "mass_flow_kg_s": "flow (kg/s)",
}

CANONICAL_FIELDS = [
    "velocity_m_s","pressure_Pa","temperature_K",
    "density_kg_m3","rpm","liquid_volume_fraction",
]

def to_canonical_payload(df: pd.DataFrame):
    if df is None or df.empty: return []
    base_cols = [c for c in CANONICAL_FIELDS if c in df.columns]
    if not base_cols:
        if "pressure_bar" in df.columns: df["pressure_Pa"] = df["pressure_bar"]*1e5
        if "temperature_C" in df.columns: df["temperature_K"] = df["temperature_C"]+273.15
        if "rpm_k" in df.columns: df["rpm"] = df["rpm_k"]*1000.0
        base_cols = [c for c in CANONICAL_FIELDS if c in df.columns]
    return df[base_cols].to_dict(orient="records") if base_cols else []

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

def show_bc(container, bc_dict: dict):
    container.empty()
    st.session_state["rev_live"] += 1
    rev = st.session_state["rev_live"]
    with container.container():
        st.subheader("BC Recommendation (JSON)")
        st.json(bc_dict)
        st.download_button(
            "⬇️ Download BC JSON",
            data=json.dumps(bc_dict, indent=2),
            file_name=f"bc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
            key=f"dl_bc_{rev}",
        )

def health_emoji(val, ok, warn):
    if val is None: return ""
    try: v = float(val)
    except: return ""
    return "✅" if v >= ok else ("⚠️" if v >= warn else "🔴")

def vib_emoji(v):
    try: v = float(v)
    except: return ""
    return "✅" if v <= 4 else ("⚠️" if v <= 7 else "🔴")

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Live section
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("### 📡 Live Telemetry")

kpi_ph    = st.empty()
health_ph = st.empty()
press_ph  = st.empty()
temp_ph   = st.empty()
kin_ph    = st.empty()
dens_ph   = st.empty()
flow_ph   = st.empty()
dl_ph     = st.empty()
bc_ph     = st.empty()

def render_live_once():
    df = fetch_recent(int(limit))
    if df.empty:
        for ph in [kpi_ph, health_ph, press_ph, temp_ph, kin_ph, dens_ph, flow_ph, dl_ph]:
            ph.empty()
        st.info("No samples yet. Start the simulator (see README).")
        return None, None

    df = add_derived(df)
    tail = df.tail(int(limit)).copy()
    latest = tail.iloc[-1].to_dict()

    # ── KPIs (top row) ──
    with kpi_ph.container():
        st.markdown("#### Latest KPIs")
        # preferred ordering
        kpis = []
        for key in ["pressure_bar","temperature_C","velocity_m_s","rpm_k","liquid_volume_fraction","mass_flow_kg_s"]:
            if key in tail.columns: kpis.append(key)
        cols = st.columns(len(kpis)) if kpis else [st.container()]
        for i, c in enumerate(kpis):
            label = FRIENDLY.get(c, c)
            val = latest.get(c)
            if val is None and c == "pressure_bar" and "pressure_Pa" in latest:
                val = float(latest["pressure_Pa"])/1e5
            if val is None and c == "temperature_C" and "temperature_K" in latest:
                val = float(latest["temperature_K"])-273.15
            if val is None and c == "rpm_k" and "rpm" in latest:
                val = float(latest["rpm"])/1000.0
            # format
            if isinstance(val,(int,float)):
                if c=="pressure_bar": val=f"{val:.3f}"
                elif c=="temperature_C": val=f"{val:.2f}"
                elif c=="velocity_m_s": val=f"{val:.3f}"
                elif c=="rpm_k": val=f"{val:.2f}"
                elif c=="liquid_volume_fraction": val=f"{val:.4f}"
                elif c=="mass_flow_kg_s": val=f"{val:.2f}"
            cols[i].metric(label, val if val is not None else "—")

    # ── Health badges (single line) ──
    with health_ph.container():
        parts = []
        if "lube_oil_bar" in tail.columns:
            lo = latest.get("lube_oil_bar")
            parts.append(f"{health_emoji(lo, 2.0, 1.5)} lube oil: {lo:.2f} bar" if isinstance(lo,(int,float)) else "")
        if "bearing_temp_C" in tail.columns:
            bt = latest.get("bearing_temp_C")
            parts.append(f"{'✅' if bt<=80 else ('⚠️' if bt<=95 else '🔴')} bearing temp: {bt:.1f} °C" if isinstance(bt,(int,float)) else "")
        # max vibration across channels if present
        vib_vals = []
        for k in ["vib_ax_mm_s","vib_v_mm_s","vib_h_mm_s"]:
            if k in tail.columns and pd.notna(latest.get(k)):
                vib_vals.append(float(latest.get(k)))
        if vib_vals:
            mv = max(vib_vals)
            parts.append(f"{vib_emoji(mv)} vibration: {mv:.1f} mm/s")
        if "seal_leak_l_min" in tail.columns:
            sl = latest.get("seal_leak_l_min")
            parts.append(f"{'✅' if sl<=1 else ('⚠️' if sl<=3 else '🔴')} seal leak: {sl:.1f} L/min" if isinstance(sl,(int,float)) else "")
        if parts:
            st.caption(" · ".join([p for p in parts if p]))

    # ── Charts by compatible scales ──
    # Pressure (bar): pressure_bar, P2_bar, lube_oil_bar
    with press_ph.container():
        cols = []
        series = {}
        if "pressure_bar" in tail.columns: series["Pressure (bar)"] = tail["pressure_bar"]
        if "P2_bar" in tail.columns:       series["P2 (bar)"]       = tail["P2_bar"]
        if "lube_oil_bar" in tail.columns: series["Lube oil (bar)"]  = tail["lube_oil_bar"]
        if series:
            st.markdown("#### Pressure (bar)")
            plot_df = pd.DataFrame(series)
            if "timestamp_utc" in tail.columns:
                try: plot_df.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            st.line_chart(plot_df, height=220, use_container_width=True)

    # Temperature (°C): temperature_C, T2_C, bearing_temp_C
    with temp_ph.container():
        series = {}
        if "temperature_C" in tail.columns: series["T1 (°C)"] = tail["temperature_C"]
        if "T2_C" in tail.columns:          series["T2 (°C)"] = tail["T2_C"]
        if "bearing_temp_C" in tail.columns:series["Bearing (°C)"] = tail["bearing_temp_C"]
        if series:
            st.markdown("#### Temperature (°C)")
            plot_df = pd.DataFrame(series)
            if "timestamp_utc" in tail.columns:
                try: plot_df.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            st.line_chart(plot_df, height=220, use_container_width=True)

    # Kinematics: velocity_m_s (m/s) AND rpm_k (kRPM) → two small charts to avoid rescaling
    with kin_ph.container():
        sub1, sub2 = st.columns(2)
        if "velocity_m_s" in tail.columns:
            df_u = pd.DataFrame({"Velocity (m/s)": tail["velocity_m_s"]})
            if "timestamp_utc" in tail.columns:
                try: df_u.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            with sub1: st.markdown("#### Velocity (m/s)"); st.line_chart(df_u, height=200, use_container_width=True)
        if "rpm_k" in tail.columns:
            df_r = pd.DataFrame({"RPM (×1000)": tail["rpm_k"]})
            if "timestamp_utc" in tail.columns:
                try: df_r.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            with sub2: st.markdown("#### RPM (×1000)"); st.line_chart(df_r, height=200, use_container_width=True)

    # Density & LVF
    with dens_ph.container():
        sub1, sub2 = st.columns(2)
        if "density_kg_m3" in tail.columns:
            df_d = pd.DataFrame({"Density (kg/m³)": tail["density_kg_m3"]})
            if "timestamp_utc" in tail.columns:
                try: df_d.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            with sub1: st.markdown("#### Density (kg/m³)"); st.line_chart(df_d, height=200, use_container_width=True)
        if "LVF_pct" in tail.columns:
            df_l = pd.DataFrame({"LVF (%)": tail["LVF_pct"]})
            if "timestamp_utc" in tail.columns:
                try: df_l.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            with sub2: st.markdown("#### LVF (%)"); st.line_chart(df_l, height=200, use_container_width=True)

    # Flow & Valves/IGV (%)
    with flow_ph.container():
        sub1, sub2 = st.columns(2)
        if "mass_flow_kg_s" in tail.columns:
            df_f = pd.DataFrame({"Flow (kg/s)": tail["mass_flow_kg_s"]})
            if "timestamp_utc" in tail.columns:
                try: df_f.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            with sub1: st.markdown("#### Flow (kg/s)"); st.line_chart(df_f, height=200, use_container_width=True)
        pct_series = {}
        if "valve_pct" in tail.columns: pct_series["Valve (%)"] = tail["valve_pct"]
        if "igv_pct" in tail.columns:   pct_series["IGV (%)"]   = tail["igv_pct"]
        if pct_series:
            df_p = pd.DataFrame(pct_series)
            if "timestamp_utc" in tail.columns:
                try: df_p.index = pd.to_datetime(tail["timestamp_utc"], errors="coerce")
                except Exception: pass
            with sub2: st.markdown("#### Valve / IGV (%)"); st.line_chart(df_p, height=200, use_container_width=True)

    # Download recent (canonical JSON)
    payload = to_canonical_payload(tail)
    dl_ph.empty()
    dl_ph.download_button(
        "⬇️ Download recent samples (JSON)",
        data=json.dumps(payload, indent=2),
        file_name=f"recent_samples_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        use_container_width=True,
        key=f"dl_recent_{datetime.utcnow().strftime('%H%M%S%f')}"
    )

    return tail, payload

tail_df, current_payload = render_live_once()

# Generate BC
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
    show_bc(bc_ph, st.session_state.bc_live)

# Auto refresh loop (keeps BC visible as-is)
with st.container():
    if auto_refresh:
        for _ in range(max(1, int(60 / max(int(refresh_s), 1)))):
            time.sleep(int(refresh_s))
            tail_df, current_payload = render_live_once()
            if st.session_state.bc_live:
                show_bc(bc_ph, st.session_state.bc_live)

st.markdown("---")
st.caption(f"Backend: {BACKEND_URL} • Endpoints: POST /recommend-bc, GET /recent-wgc")

