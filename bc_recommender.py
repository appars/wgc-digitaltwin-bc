# bc_recommender.py
import math
from statistics import mean
from typing import List, Dict, Any, Optional

# Defaults (tweak as needed)
DEFAULT_RHO = 1.2          # kg/m^3
DEFAULT_MU  = 1.8e-5       # Pa·s
DEFAULT_D   = 0.5          # m, characteristic diameter/length

def _safe_mean(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return mean(xs) if xs else None

def _choose_turbulence_model(Re: Optional[float]) -> str:
    if Re is None:
        return "k-omega SST"
    if Re < 1e5:
        return "k-epsilon"
    if Re <= 1e6:
        return "k-omega SST"
    return "LES"

def recommend_bc(samples: List[Dict[str, Any]], meta: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Computes simple BCs from telemetry:
    - inlet_pressure:       mean(pressure_Pa) in BAR
    - outlet_pressure:      inlet_pressure + delta (estimated from rpm/velocity)
    - inlet_temperature:    mean(temperature_K)
    - turbulence_model:     from Reynolds number using mean velocity/density and DEFAULT_D, DEFAULT_MU

    inputs: list of dicts with keys like velocity_m_s, pressure_Pa, temperature_K, density_kg_m3, rpm
    """
    meta = meta or {}
    D  = float(meta.get("characteristic_length_m", DEFAULT_D))
    mu = float(meta.get("dynamic_viscosity_Pa_s", DEFAULT_MU))

    v  = _safe_mean([s.get("velocity_m_s")      for s in samples if isinstance(s, dict)])
    pP = _safe_mean([s.get("pressure_Pa")       for s in samples if isinstance(s, dict)])
    TK = _safe_mean([s.get("temperature_K")     for s in samples if isinstance(s, dict)])
    rho= _safe_mean([s.get("density_kg_m3")     for s in samples if isinstance(s, dict)]) or DEFAULT_RHO
    rpm= _safe_mean([s.get("rpm")               for s in samples if isinstance(s, dict)])

    # Inlet pressure as BAR from mean pressure_Pa (if not provided, assume ~1.013 bar)
    inlet_bar = (pP / 1e5) if pP is not None else 1.013

    # Estimate outlet as inlet + delta_bar using rpm/velocity as signals (demo heuristic)
    delta_bar = 0.5  # base boost
    if rpm is not None:
        # add small adjustment around 15k rpm
        delta_bar += 0.00002 * (rpm - 15000.0)
    if v is not None:
        # velocity hint (a touch more if higher v)
        delta_bar += 0.01 * max(0.0, (v - 20.0) / 5.0)

    outlet_bar = max(inlet_bar + delta_bar, inlet_bar + 0.1)  # ensure > inlet

    # Temperature (K) from mean
    inlet_T = TK if TK is not None else 300.0

    # Reynolds number for turbulence model
    Re = None
    if v is not None and mu > 0 and D > 0:
        Re = (rho * v * D) / mu

    turb = _choose_turbulence_model(Re)

    # Round for tidy UI
    def r(x, nd=3):
        try:
            return round(float(x), nd)
        except Exception:
            return x

    return {
        "inlet_pressure": r(inlet_bar, 3),         # bar
        "outlet_pressure": r(outlet_bar, 3),       # bar
        "inlet_temperature": r(inlet_T, 2),        # K
        "turbulence_model": turb,                  # string
        "derived": {
            "Re": r(Re, 0) if Re is not None else None,
            "rho_used": r(rho, 3),
            "mu_used": mu,
            "D_used": D
        },
        "notes": "Data-driven BC; tweak heuristics as needed."
    }

