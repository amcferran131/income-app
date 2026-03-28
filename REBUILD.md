# Dividend Atlas — Full Rebuild Guide

This document covers everything needed to rebuild the Personal Portfolio Income Calculator
from scratch using the source at https://github.com/amcferran131/income-app.

---

## Architecture Overview

| Layer | Technology | Host |
|-------|-----------|------|
| Backend API | Python / Flask / yfinance | Railway |
| Frontend | React 18 / Vite / Recharts | Vercel |

The frontend calls the Railway API directly from the browser.
CORS is locked to the Vercel domain in `api.py`.

**Live URLs**
- API: `https://dividend-api-production.up.railway.app`
- Frontend: `https://dividend-calculator-blond.vercel.app`

---

## Prerequisites

| Tool | Minimum version | Install |
|------|----------------|---------|
| Python | 3.10+ | https://python.org |
| pip | bundled with Python | — |
| Node.js | 18+ | https://nodejs.org |
| npm | bundled with Node | — |
| Git | any recent | https://git-scm.com |
| Railway CLI | latest | `npm install -g @railway/cli` |
| Vercel CLI | latest | `npm install -g vercel` |

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/amcferran131/income-app.git
cd income-app
```

---

## Step 2 — Backend (Flask API)

### 2a. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
```

### 2b. Install Python dependencies

```bash
pip install -r requirements.txt
```

Dependencies (`requirements.txt`):
- `flask==3.1.3`
- `yfinance==1.0`
- `pandas==2.3.3`
- `gunicorn==23.0.0`

### 2c. Run locally

```bash
python api.py
# API available at http://127.0.0.1:5000
```

Test it:
```bash
curl "http://127.0.0.1:5000/dividends?tickers=O,JEPI"
```

### 2d. Deploy to Railway

1. Log in: `railway login`
2. Create a new project: `railway init`
3. Link to this repo or deploy directly:
   ```bash
   railway up
   ```
4. Railway auto-detects the `Procfile`:
   ```
   web: gunicorn api:app --bind 0.0.0.0:$PORT
   ```
   No environment variables are required — Railway injects `$PORT` automatically.

5. After deploy, copy the Railway public URL (e.g. `https://dividend-api-production.up.railway.app`).

---

## Step 3 — Frontend (React / Vite)

### 3a. Install Node dependencies

```bash
npm install
```

Key dependencies (`package.json`):
- `react` ^18.3.1
- `react-dom` ^18.3.1
- `recharts` ^2.12.7
- `vite` ^5.4.2 (dev)
- `@vitejs/plugin-react` ^4.3.1 (dev)

### 3b. Update the API URL (if Railway URL changes)

Two files hard-code the Railway URL — update both if you redeploy the API:

| File | Line | Value to update |
|------|------|----------------|
| `src/App.jsx` | ~82 | `fetch("https://dividend-api-production.up.railway.app/dividends", ...)` |
| `dividend_lookup.js` | 1 | `const API_BASE = 'https://dividend-api-production.up.railway.app'` |

### 3c. Update the CORS allowed origin (if Vercel URL changes)

In `api.py` line 9:
```python
ALLOWED_ORIGIN = 'https://dividend-calculator-blond.vercel.app'
```
Change this to your new Vercel URL, then redeploy the API.

### 3d. Run locally

```bash
npm run dev
# Frontend at http://localhost:5173
```

Note: Browser CORS restrictions will block local frontend → Railway API unless you
temporarily add `http://localhost:5173` to `ALLOWED_ORIGIN` in `api.py`.

### 3e. Deploy to Vercel

1. Log in: `vercel login`
2. Deploy:
   ```bash
   vercel --prod
   ```
3. Vercel reads `vercel.json` which rewrites all routes to `index.html` for SPA routing:
   ```json
   { "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
   ```
4. Vercel builds with `npm run build` (Vite outputs to `dist/`) automatically.
5. Copy the Vercel URL and update `ALLOWED_ORIGIN` in `api.py` if it changed, then
   redeploy the API.

---

## Step 4 — Verify end-to-end

```bash
# 1. Hit the API directly
curl "https://dividend-api-production.up.railway.app/dividends?tickers=O,JEPI,KO"

# 2. Open the frontend in a browser
open https://dividend-calculator-blond.vercel.app

# 3. Use the "Lookup" button on any ticker row to confirm the frontend ↔ API round-trip
```

---

## File Map

```
income-app/
├── api.py                          # Flask API — /dividends endpoint
├── dividend_lookup.js              # JS client helper (imports fetchDividends)
├── requirements.txt                # Python deps
├── Procfile                        # Railway process declaration
├── index.html                      # Vite HTML entry point
├── vite.config.js                  # Vite + React plugin config
├── package.json                    # Node deps and npm scripts
├── vercel.json                     # Vercel SPA rewrite rule
├── src/
│   ├── main.jsx                    # React entry — mounts <App />
│   └── App.jsx                     # Full dashboard UI component
├── personal-portfolio-income-calculator (1).jsx   # Standalone JSX prototype
├── run_me.py                       # Local helper / quick-start script
└── test_yahoo.py                   # yfinance smoke tests
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| CORS error in browser | `ALLOWED_ORIGIN` mismatch | Update `api.py` and redeploy API |
| `No price data` for a ticker | Yahoo Finance symbol format | Add translation to `TRANSLATIONS` dict in `api.py` |
| Railway deploy fails | Missing `Procfile` or wrong Python version | Ensure `Procfile` exists and Python 3.10+ is set in Railway settings |
| Vercel build fails | Node version too old | Set Node 18+ in Vercel project settings |
| `0` dividends returned | Ticker pays no dividends or < 24 months of history | Expected — non-dividend tickers return `payment_frequency: 0` |
