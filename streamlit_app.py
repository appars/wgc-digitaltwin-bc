# streamlit_app.py
import os, json, time, math, random
from datetime import datetime

import requests
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# Page setup
# -----------------------------------------------------------------------------
st.set_page_config(page_title="WGC Digital Twin — Dashboard & BC Recommender", layout="wide")

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

st.title("Wet Gas Compressor — Real-Time Dashboard & BC Recommender")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def post_recommend(payload):
    """POST samples (list[dict]) to /recommend-bc and return (ok, response_json or text)."""
    try:
        r = requests.post(RECOMMEND_URL, json=payload, timeout=25)
        r.raise_for_status()
        return True, r.json()
    except Exception as e:
        try:
            return False, r.text  # type: ignore
        except Exception:
            return False, str(e)

def fetch_recent(limit=200):
    """GET recent samples from backend; return DataFrame (may be empty)."""
    try:
        r = requests.get(RECENT_URL, params={"limit": limit}, timeout=15)
        r.raise_for_status()
        data = r.json().get("samples", [])
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        st.error(f"Recent fetch failed: {e}")
        return pd.DataFrame()

def add_trend_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns for trend plotting: pressure_bar, temperature_C, rpm_k."""
    df = df.copy()
    if "pressure_Pa" in df.columns:
        df["pressure_bar"] = pd.to_numeric(df["pressure_Pa"], errors="coerce") / 1e5
    if "temperature_K" in df.columns:
        df["temperature_C"] = pd.to_numeric(df["temperature_K"], errors="coerce") - 273.15
    if "rpm" in df.columns:
        df["rpm_k"] = pd.to_numeric(df["rpm"], errors="coerce") / 1000.0
    return df

def unit_of(field: str):
    f = field.lower()
    if f == "pressure_bar" or "pressure" in f: return "bar"
    if f == "temperature_c": return "°C"
    if f.endswith("_k") or "temperature" in f: return "K"
    if f == "rpm_k": return "kRPM"
    if f == "rpm": return "rpm"
    if "velocity" in f and f.endswith("_m_s"): return "m/s"
    if "density" in f: return "kg/m³"
    return None

def render_value(field: str, value):
    try:
        v = float(value)
    except Exception:
        return str(value)
    f = field.lower()
    if f == "pressure_bar" or "pressure" in f: return f"{v:.3f}"
    if f == "temperature_c": return f"{v:.2f}"
    if f.endswith("_k") or "temperature" in f: return f"{v:.2f}"
    if f == "rpm_k": return f"{v:.2f}"
    if f == "rpm": return f"{v:.0f}"
    if "velocity" in f and f.endswith("_m_s"): return f"{v:.3f}"
    if "density" in f: return f"{v:.3f}"
    return f"{v:.3f}"

FRIENDLY_LABELS = {
    "pressure_bar":  "pressure (bar)",
    "temperature_C": "temperature (°C)",
    "rpm_k":         "rpm (kRPM)",
    "density_kg_m3": "density (kg/m³)",
    "velocity_m_s":  "velocity (m/s)",
}

# Canonical format used for Upload/Paste
CANONICAL_FIELDS = [
    "velocity_m_s",
    "pressure_Pa",
    "temperature_K",
    "density_kg_m3",
    "rpm",
    "liquid_volume_fraction",
]

def to_canonical_records(df: pd.DataFrame):
    """Return a list of dicts containing ONLY canonical fields (no timestamp / derived)."""
    if df is None or df.empty:
        return []
    rows = []
    for _, row in df.iterrows():
        rec = {}
        for k in CANONICAL_FIELDS:
            if k in df.columns:
                val = row.get(k)
                if pd.notna(val):
                    rec[k] = val
        if rec:
            rows.append(rec)
    return rows

def render_bc_result(ok, res, container):
    """
    Standard BC renderer:
    - enforce notes text,
    - show BC JSON first,
    - then download button,
    - then server link.
    """
    if not ok:
        container.error(str(res))
        return

    # normalize BC content
    bc = None
    if isinstance(res, dict) and "bc" in res:
        bc = res.get("bc")
    if not isinstance(bc, dict):
        bc = res if isinstance(res, dict) else None
    if bc is None:
        try:
            container.json(res if isinstance(res, (dict, list)) else json.loads(res))
        except Exception:
            container.code(str(res))
        return

    # enforce notes text
    bc = dict(bc)
    bc["notes"] = "Data-driven BC; tweak heuristics as needed."

    container.subheader("BC Recommendation (JSON)")
    container.json(bc)
    container.download_button(
        "⬇️ Download BC JSON",
        data=json.dumps(bc, indent=2),
        file_name=f"bc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        use_container_width=True,
    )
    if isinstance(res, dict) and "download" in res:
        container.markdown(f"[Download Boundary Conditions]({BACKEND_URL}{res['download']})")

# -----------------------------------------------------------------------------
# Sidebar Controls
# -----------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Backend")
    st.text_input("Backend URL", BACKEND_URL, disabled=True, key="bk_url_display")
    st.caption("Endpoints: POST /recommend-bc, GET /recent-wgc")
    st.divider()
    st.subheader("Live Telemetry")
    default_limit = st.number_input("Rows to pull", min_value=50, max_value=5000, value=200, step=50, key="rows_pull")
    refresh_s     = st.number_input("Auto refresh (s)", min_value=1, max_value=30, value=3, step=1, key="refresh_rate")
    auto_refresh  = st.toggle("Auto refresh live telemetry", value=True, key="toggle_autorefresh")
    st.caption("Tip: turn off auto refresh to freeze the dashboard while presenting.")

# -----------------------------------------------------------------------------
# Tabs
# -----------------------------------------------------------------------------
tab_dash, tab_upload, tab_paste, tab_synth = st.tabs([
    "📡 Live Dashboard", "📁 Upload JSON", "✍️ Paste JSON", "⚙️ Generate Synthetic"
])

# -----------------------------------------------------------------------------
# LIVE DASHBOARD
# -----------------------------------------------------------------------------
with tab_dash:
    st.subheader("Live Telemetry")

    limit = int(default_limit)

    kpi_ph     = st.empty()
    trends_hdr = st.empty()
    trends_ph  = st.empty()
    table_ph   = st.empty()
    info_ph    = st.empty()
    dl_ph      = st.empty()
    bc_ph      = st.empty()

    gen_btn = st.button("Generate & Download BC from shown samples", type="primary", key="btn_live_gen")

    def render_once():
        df = fetch_recent(limit)

        if df.empty:
            kpi_ph.empty(); trends_hdr.empty(); trends_ph.empty()
            table_ph.write("No samples yet. Start the simulator.")
            info_ph.warning("No data returned.")
            dl_ph.empty(); bc_ph.empty()
            return None, None

        # copy before derived (for canonical download)
        df_raw_for_export = df.copy()

        # reorder and derive
        cols = list(df.columns)
        if "timestamp_utc" in cols:
            cols.remove("timestamp_utc")
            cols = ["timestamp_utc"] + cols
        df = df[cols]
        df = add_trend_columns(df)

        # KPIs
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        latest = df.iloc[-1].to_dict()

        kpi_ph.empty()
        with kpi_ph.container():
            st.markdown("#### Latest KPIs")
            preferred = ["pressure_bar", "temperature_C", "density_kg_m3", "velocity_m_s", "rpm_k"]
            kpis = [c for c in preferred if c in df.columns]
            for c in num_cols:
                if c not in kpis and len(kpis) < 6:
                    kpis.append(c)
            if not kpis:
                st.info("No numeric fields found.")
            else:
                cols_ui = st.columns(len(kpis))
                for i, c in enumerate(kpis[:6]):
                    label = FRIENDLY_LABELS.get(c, c)
                    if c == "pressure_bar":
                        val = latest.get("pressure_bar")
                        if val is None and "pressure_Pa" in latest: val = float(latest["pressure_Pa"]) / 1e5
                    elif c == "temperature_C":
                        val = latest.get("temperature_C")
                        if val is None and "temperature_K" in latest: val = float(latest["temperature_K"]) - 273.15
                    elif c == "rpm_k":
                        val = latest.get("rpm_k")
                        if val is None and "rpm" in latest: val = float(latest["rpm"]) / 1000.0
                    else:
                        val = latest.get(c)
                    cols_ui[i].metric(label, render_value(c, val))

        # Trends (combined)
        trends_hdr.empty(); trends_ph.empty()
        trend_cols = []
        if "pressure_bar" in df.columns:  trend_cols.append("pressure_bar")
        if "density_kg_m3" in df.columns: trend_cols.append("density_kg_m3")
        if "temperature_C" in df.columns: trend_cols.append("temperature_C")
        if "velocity_m_s" in df.columns:  trend_cols.append("velocity_m_s")
        if "rpm_k" in df.columns:         trend_cols.append("rpm_k")

        if trend_cols:
            with trends_hdr.container():
                st.markdown("#### Trends (combined)")
                st.caption("Pressure in bar, Temperature in °C, RPM in ×1000.")
            plot_df = df[trend_cols].copy()
            plot_df.rename(columns={
                "pressure_bar":   "Pressure (bar)",
                "density_kg_m3":  "Density (kg/m³)",
                "temperature_C":  "Temperature (°C)",
                "velocity_m_s":   "Velocity (m/s)",
                "rpm_k":          "RPM (×1000)",
            }, inplace=True)
            if "timestamp_utc" in df.columns:
                try:
                    plot_df.index = pd.to_datetime(df["timestamp_utc"], errors="coerce")
                except Exception:
                    pass
            with trends_ph.container():
                st.line_chart(plot_df, height=220, use_container_width=True)
        else:
            with trends_ph.container():
                st.info("No trend-friendly fields available.")

        # Table
        table_ph.dataframe(df.tail(limit), use_container_width=True, height=380)
        info_ph.caption(f"Last updated: {datetime.utcnow().isoformat()}Z — showing {len(df)} rows")

        # Canonical download (no timestamp/derived)
        canonical_payload = to_canonical_records(df_raw_for_export.tail(limit))
        dl_ph.download_button(
            "⬇️ Download recent samples (JSON)",
            data=json.dumps(canonical_payload, indent=2),
            file_name=f"recent_samples_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )

        return df.tail(limit), canonical_payload

    current_df, current_canonical = render_once()

    if gen_btn:
        if not current_canonical:
            bc_ph.warning("No data available to generate BC.")
        else:
            with bc_ph:
                with st.spinner("Requesting recommendation for shown samples..."):
                    ok, res = post_recommend(current_canonical)
                render_bc_result(ok, res, bc_ph)

    if auto_refresh:
        loops = max(1, int(180 / max(refresh_s, 1)))
        for _ in range(loops):
            time.sleep(refresh_s)
            current_df, current_canonical = render_once()

# -----------------------------------------------------------------------------
# UPLOAD JSON
# -----------------------------------------------------------------------------
with tab_upload:
    st.subheader("Upload telemetry JSON")
    st.caption("Upload a JSON array in canonical format: velocity_m_s, pressure_Pa, temperature_K, density_kg_m3, rpm, liquid_volume_fraction.")
    up = st.file_uploader("Choose a JSON file", type=["json"], key="upload_file")

    up_preview_ph = st.empty()
    up_result_ph  = st.empty()

    if up is not None:
        try:
            payload = json.load(up)
            if not isinstance(payload, list):
                st.error("Uploaded JSON must be a list of sample objects.")
            else:
                df = pd.DataFrame(payload)
                st.success(f"Loaded {len(df)} samples.")
                up_preview_ph.dataframe(add_trend_columns(df.copy()).head(200), use_container_width=True)
                if st.button("Recommend BC (uploaded)", type="primary", key="btn_bc_uploaded"):
                    with st.spinner("Requesting recommendation..."):
                        ok, res = post_recommend(payload)
                    up_result_ph.empty()
                    render_bc_result(ok, res, up_result_ph)
        except Exception as e:
            st.error(f"Parse error: {e}")

# -----------------------------------------------------------------------------
# PASTE JSON
# -----------------------------------------------------------------------------
with tab_paste:
    st.subheader("Paste telemetry JSON")
    starter = """[
  {"velocity_m_s": 22.8, "pressure_Pa": 200500, "temperature_K": 300.2, "density_kg_m3": 1.2, "rpm": 14980, "liquid_volume_fraction": 0.011},
  {"velocity_m_s": 23.1, "pressure_Pa": 200300, "temperature_K": 300.0, "density_kg_m3": 1.2, "rpm": 15020, "liquid_volume_fraction": 0.012}
]"""
    pasted = st.text_area("JSON array", value=starter, height=220, key="pasted_json")

    paste_preview_ph = st.empty()
    paste_result_ph  = st.empty()

    # Live preview (best-effort)
    try:
        tmp = json.loads(pasted)
        if isinstance(tmp, list) and tmp:
            paste_preview_ph.dataframe(add_trend_columns(pd.DataFrame(tmp)).head(200), use_container_width=True)
    except Exception:
        paste_preview_ph.info("Paste valid JSON array to preview.")

    if st.button("Recommend BC (pasted)", key="btn_bc_pasted"):
        try:
            payload = json.loads(pasted)
            if not isinstance(payload, list):
                st.error("Payload must be a JSON array (list) of objects.")
            else:
                with st.spinner("Requesting recommendation..."):
                    ok, res = post_recommend(payload)
                paste_result_ph.empty()
                render_bc_result(ok, res, paste_result_ph)
        except Exception as e:
            st.error(f"JSON parse error: {e}")

# -----------------------------------------------------------------------------
# SYNTHETIC
# -----------------------------------------------------------------------------
with tab_synth:
    st.subheader("Generate synthetic samples")
    cnt = st.slider("Number of samples", 5, 500, 50, step=5, key="synthetic_count")

    synth_preview_ph = st.empty()
    synth_result_ph  = st.empty()

    if st.button("Generate & Recommend", key="btn_bc_synth"):
        payload = make_synthetic(cnt)
        st.info(f"Generated {len(payload)} synthetic samples.")
        df = pd.DataFrame(payload)
        if not df.empty:
            synth_preview_ph.dataframe(add_trend_columns(df.copy()).head(200), use_container_width=True)
        with st.spinner("Requesting recommendation..."):
            ok, res = post_recommend(payload)
        synth_result_ph.empty()
        render_bc_result(ok, res, synth_result_ph)

# -----------------------------------------------------------------------------
st.markdown("---")
st.caption(f"Backend: {BACKEND_URL} • Endpoints: POST /recommend-bc, GET /recent-wgc")

