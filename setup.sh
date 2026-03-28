#!/usr/bin/env bash
# setup.sh — Full automated install and deploy for Dividend Atlas
# Source: https://github.com/amcferran131/income-app
#
# Usage:
#   bash setup.sh              # clone, install, and deploy everything
#   bash setup.sh --local      # clone and install only (no deploy)
#   bash setup.sh --api-only   # deploy API to Railway only
#   bash setup.sh --frontend-only  # deploy frontend to Vercel only

set -euo pipefail

REPO_URL="https://github.com/amcferran131/income-app.git"
PROJECT_DIR="income-app"

# ─── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ─── Parse flags ───────────────────────────────────────────────────────────────
LOCAL_ONLY=false
API_ONLY=false
FRONTEND_ONLY=false
for arg in "$@"; do
  case $arg in
    --local)         LOCAL_ONLY=true ;;
    --api-only)      API_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
  esac
done

# ─── 1. Dependency checks ──────────────────────────────────────────────────────
info "Checking prerequisites..."

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    error "$1 is not installed. See REBUILD.md Prerequisites section."
  fi
  info "  $1 found: $(command -v "$1")"
}

check_cmd git
check_cmd python3
check_cmd pip3
check_cmd node
check_cmd npm

if [ "$LOCAL_ONLY" = false ]; then
  check_cmd railway || { warn "Railway CLI not found — installing..."; npm install -g @railway/cli; }
  check_cmd vercel  || { warn "Vercel CLI not found — installing...";  npm install -g vercel; }
fi

# ─── 2. Clone repo ─────────────────────────────────────────────────────────────
if [ -d "$PROJECT_DIR" ]; then
  warn "Directory '$PROJECT_DIR' already exists — pulling latest changes instead."
  cd "$PROJECT_DIR"
  git pull
else
  info "Cloning $REPO_URL..."
  git clone "$REPO_URL"
  cd "$PROJECT_DIR"
fi

# ─── 3. Python / API setup ─────────────────────────────────────────────────────
if [ "$FRONTEND_ONLY" = false ]; then
  info "Setting up Python virtual environment..."
  python3 -m venv venv

  # Activate (works on Linux/macOS; Windows users run: venv\Scripts\activate manually)
  # shellcheck disable=SC1091
  source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null \
    || warn "Could not auto-activate venv — activate it manually before running the API."

  info "Installing Python dependencies..."
  pip3 install -r requirements.txt --quiet

  info "Python setup complete."
  info "  Local API: python api.py  →  http://127.0.0.1:5000"
fi

# ─── 4. Node / Frontend setup ──────────────────────────────────────────────────
if [ "$API_ONLY" = false ]; then
  info "Installing Node dependencies..."
  npm install --silent

  info "Node setup complete."
  info "  Local dev server: npm run dev  →  http://localhost:5173"
fi

# ─── 5. Deploy — Railway (API) ─────────────────────────────────────────────────
if [ "$LOCAL_ONLY" = false ] && [ "$FRONTEND_ONLY" = false ]; then
  info "Deploying API to Railway..."
  echo ""
  echo "  Railway will prompt you to log in if you haven't already."
  echo "  When asked, link this deploy to an existing or new Railway project."
  echo ""

  railway login

  # Init project if no .railway dir
  if [ ! -d ".railway" ]; then
    railway init
  fi

  railway up

  info "API deployed. Copy the Railway public URL shown above."
  echo ""
  read -r -p "  Paste your Railway API URL (e.g. https://xyz.up.railway.app): " RAILWAY_URL

  if [ -n "$RAILWAY_URL" ]; then
    info "Updating API URL in src/App.jsx and dividend_lookup.js..."
    # Replace old Railway URL with newly provided one (handles any domain)
    sed -i "s|https://dividend-api-production\.up\.railway\.app|${RAILWAY_URL}|g" src/App.jsx
    sed -i "s|https://dividend-api-production\.up\.railway\.app|${RAILWAY_URL}|g" dividend_lookup.js
    info "  Updated src/App.jsx"
    info "  Updated dividend_lookup.js"
  fi
fi

# ─── 6. Deploy — Vercel (Frontend) ────────────────────────────────────────────
if [ "$LOCAL_ONLY" = false ] && [ "$API_ONLY" = false ]; then
  info "Deploying frontend to Vercel..."
  echo ""
  echo "  Vercel will prompt you to log in if you haven't already."
  echo "  Accept defaults or link to an existing project."
  echo ""

  vercel --prod

  info "Frontend deployed."
  echo ""
  read -r -p "  Paste your Vercel URL (e.g. https://myapp.vercel.app): " VERCEL_URL

  if [ -n "$VERCEL_URL" ]; then
    info "Updating CORS allowed origin in api.py..."
    OLD_ORIGIN="https://dividend-calculator-blond.vercel.app"
    sed -i "s|${OLD_ORIGIN}|${VERCEL_URL}|g" api.py
    info "  Updated api.py ALLOWED_ORIGIN to ${VERCEL_URL}"

    info "Redeploying API with updated CORS origin..."
    railway up
  fi
fi

# ─── 7. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Setup complete."
echo ""

if [ "$LOCAL_ONLY" = true ]; then
  echo "  Start the API:      source venv/bin/activate && python api.py"
  echo "  Start the frontend: npm run dev"
else
  echo "  API (Railway):  ${RAILWAY_URL:-https://dividend-api-production.up.railway.app}"
  echo "  Frontend:       ${VERCEL_URL:-https://dividend-calculator-blond.vercel.app}"
fi

echo ""
echo "  See REBUILD.md for full documentation."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
