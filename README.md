
# Wet Gas Compressor - BC Recommender Demo

## How to run locally

1. Build and start services:

```bash
docker compose up --build
```

2. Open Streamlit UI:

```
http://localhost:8501
```

3. Start simulator: it will send sample data to backend automatically.

4. Upload JSON data in Streamlit and click **Recommend BC** to get boundary conditions.

5. Optional: download BC as JSON for CFD/OpenFOAM.
