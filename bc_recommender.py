
"""
No-ML boundary condition recommender for Wet Gas Compressor (OpenFOAM-target).
Generates a solver-agnostic BC JSON (Tier A: single-phase) with clear notes.
"""

from statistics import mean, pstdev
from typing import List, Dict, Any
from math import isfinite

def _safe_vals(samples: List[Dict[str, Any]], key: str) -> List[float]:
    vals = []
    for s in samples:
        v = s.get(key)
        try:
            v = float(v)
            if isfinite(v):
                vals.append(v)
        except Exception:
            pass
    return vals

def _cv(vals: List[float]) -> float:
    if not vals:
        return 1.0
    mu = mean(vals)
    if mu == 0:
        return 1.0
    if len(vals) < 3:
        return 1.0
    return pstdev(vals) / abs(mu)

def recommend_bc(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Input: list of canonical samples with keys:
      velocity_m_s, pressure_Pa, temperature_K, density_kg_m3, rpm, liquid_volume_fraction
    Output: dict with inlet/outlet/turbulence and metadata (no ML).

    Heuristics:
      - Use mean of last N samples
      - If mass flow not provided, we base on pressure/temperature; here we export pressure outlet and velocity/mass-flow inlet surrogate
      - Outlet pressure assumed 1.25× inlet if no downstream signal (demo-safe)
    """
    # Use last 60 samples (or all if fewer)
    N = min(60, len(samples))
    window = samples[-N:]

    u = _safe_vals(window, "velocity_m_s")
    p = _safe_vals(window, "pressure_Pa")
    T = _safe_vals(window, "temperature_K")
    rho = _safe_vals(window, "density_kg_m3")
    rpm = _safe_vals(window, "rpm")
    lvf = _safe_vals(window, "liquid_volume_fraction")

    # Means with fallbacks
    vel = mean(u) if u else 22.0
    press_Pa = mean(p) if p else 2.0e5
    temp_K = mean(T) if T else 300.0
    dens = mean(rho) if rho else 1.2
    speed = int(mean(rpm)) if rpm else 15000
    lvf_mean = max(0.0, mean(lvf)) if lvf else 0.01

    # Derived
    press_bar = press_Pa / 1e5
    # Demo outlet assumption (increase ~25%); clamp sane range
    outlet_bar = max(press_bar * 1.05, min(press_bar * 1.35, press_bar * 1.25))

    # Steady-state check (coefficient of variation thresholds)
    cv_u = _cv(u)
    cv_p = _cv(p)
    cv_T = _cv(T)
    steady_ok = (cv_u < 0.05) and (cv_p < 0.02) and (cv_T < 0.01)

    # Turbulence defaults
    TI = 0.07  # 7%
    D = 0.5    # assumed hydraulic diameter [m]

    bc = {
        "meta": {
            "schema_version": "1.0",
            "solver": "openfoam",
            "frame": "MRF",
            "units": "SI"
        },
        "gas_model": {
            "eos": "perfectGas",
            "composition_mol": {"CH4": 0.90, "C2H6": 0.05, "CO2": 0.03, "N2": 0.02},
            "assumed": True
        },
        "inlet": {
            "type": "velocity_inlet",
            "velocity_m_s": round(vel, 4),
            "total_temperature_K": round(temp_K, 3),
            "turbulence": {"intensity": TI, "length_scale_m": round(0.1 * D, 4)},
            "multiphase": {"lvf": round(lvf_mean, 6)},
        },
        "outlet": {
            "type": "pressure_outlet",
            "static_pressure_bar": round(outlet_bar, 5)
        },
        "rotor": {"speed_rpm": int(speed)},
        "validity": {
            "steady_window_samples": N,
            "steady_ok": bool(steady_ok),
            "cv": {"velocity": round(cv_u, 4), "pressure": round(cv_p, 4), "temperature": round(cv_T, 4)}
        },
        "notes": "Data-driven BC; tweak heuristics as needed. Lean NG gas assumed; outlet pressure estimated from inlet."
    }
    return bc
