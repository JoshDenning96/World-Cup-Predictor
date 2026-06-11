# World Cup Predictor Dashboard

This folder contains a static dashboard for visualizing World Cup simulation results.

## How to run

1. Export the latest simulation data:

```bash
python3 scripts/export_simulation_json.py
```

2. Start a local web server from the `website/` directory:

```bash
python3 -m http.server 8000 --directory website
```

3. Open the dashboard in your browser:

```text
http://127.0.0.1:8000
```

## What is included

- `index.html` — dashboard UI
- `styles.css` — visual styling for a professional look
- `app.js` — client-side data loading and chart rendering
- `data/master_simulation.json` — exported simulation data from `data/processed`
