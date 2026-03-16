#!/usr/bin/env bash
# Postulio — one-shot deploy to Railway (backend) + Vercel (frontend)
# Usage: bash deploy.sh
set -e

RAILWAY_TOKEN="${RAILWAY_TOKEN:?Set RAILWAY_TOKEN env var}"
VERCEL_TOKEN="${VERCEL_TOKEN:?Set VERCEL_TOKEN env var}"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo "  Postulio Deployment Script"
echo "======================================"

# ── Prerequisites ──────────────────────────────────────────────────────────────
for cmd in node npm curl git python3; do
  command -v $cmd >/dev/null 2>&1 || { echo "ERROR: $cmd not found. Install it first."; exit 1; }
done

# Install CLIs if needed
echo ""
echo "[1/6] Installing CLIs..."
npm install -g @railway/cli vercel --quiet 2>/dev/null || {
  npm install -g @railway/cli --quiet
  npm install -g vercel --quiet
}

# ── Generate a secret key ──────────────────────────────────────────────────────
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# ── Prompt for remaining values ────────────────────────────────────────────────
echo ""
echo "[2/6] Configuration"
read -p "  Anthropic API key (sk-ant-...): " ANTHROPIC_API_KEY
read -p "  France Travail Client ID (leave blank to skip): " FT_CLIENT_ID
read -p "  France Travail Client Secret (leave blank to skip): " FT_CLIENT_SECRET

# ── Railway: create project + services ────────────────────────────────────────
echo ""
echo "[3/6] Creating Railway project..."

export RAILWAY_TOKEN

# Login via token
railway whoami || { echo "ERROR: Invalid Railway token"; exit 1; }

cd "$REPO_ROOT/backend"

# Init Railway project (non-interactive)
railway init --name "postulio" 2>/dev/null || true

# Link to project
PROJECT_ID=$(railway status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('projectId',''))" 2>/dev/null || echo "")

echo "  Project ID: $PROJECT_ID"

# Add Postgres plugin
echo "  Adding PostgreSQL..."
railway add --plugin postgresql 2>/dev/null || true

# Add Redis plugin
echo "  Adding Redis..."
railway add --plugin redis 2>/dev/null || true

# Wait for DB to provision
sleep 5

# Get DATABASE_URL from Railway
DATABASE_URL=$(railway variables --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('DATABASE_URL',''))" 2>/dev/null || echo "")
REDIS_URL=$(railway variables --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('REDIS_URL',''))" 2>/dev/null || echo "")

echo "  DATABASE_URL: ${DATABASE_URL:0:50}..."

# ── Set env vars ───────────────────────────────────────────────────────────────
echo ""
echo "[4/6] Setting environment variables..."

# We'll set these after Vercel deploy so we have the URL
railway variables set \
  ENVIRONMENT=production \
  SECRET_KEY="$SECRET_KEY" \
  ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  FRANCE_TRAVAIL_CLIENT_ID="$FT_CLIENT_ID" \
  FRANCE_TRAVAIL_CLIENT_SECRET="$FT_CLIENT_SECRET" \
  ALLOWED_ORIGINS="http://localhost:3000" \
  STORAGE_PATH="/app/storage" \
  2>/dev/null || true

# ── Deploy backend ─────────────────────────────────────────────────────────────
echo ""
echo "[5/6] Deploying backend to Railway..."
cd "$REPO_ROOT/backend"
railway up --detach 2>/dev/null || railway deploy 2>/dev/null || true

# Get backend URL
sleep 10
BACKEND_URL=$(railway domain 2>/dev/null | grep -o 'https://[^ ]*' | head -1 || echo "")
if [ -z "$BACKEND_URL" ]; then
  # Generate a domain
  railway domain generate 2>/dev/null || true
  sleep 5
  BACKEND_URL=$(railway domain 2>/dev/null | grep -o 'https://[^ ]*' | head -1 || echo "")
fi

echo "  Backend URL: $BACKEND_URL"

# Update ALLOWED_ORIGINS placeholder — will update again after Vercel
if [ -n "$BACKEND_URL" ]; then
  railway variables set ALLOWED_ORIGINS="$BACKEND_URL" 2>/dev/null || true
fi

# ── Deploy frontend to Vercel ─────────────────────────────────────────────────
echo ""
echo "[6/6] Deploying frontend to Vercel..."
cd "$REPO_ROOT/frontend"

# Set env var and deploy
VERCEL_ARGS="--token $VERCEL_TOKEN --yes --prod"
[ -n "$BACKEND_URL" ] && VERCEL_ARGS="$VERCEL_ARGS -e NEXT_PUBLIC_API_URL=$BACKEND_URL"

FRONTEND_URL=$(vercel $VERCEL_ARGS 2>&1 | grep -o 'https://[^ ]*\.vercel\.app' | tail -1 || echo "")

echo "  Frontend URL: $FRONTEND_URL"

# ── Update CORS with real Vercel URL ──────────────────────────────────────────
if [ -n "$FRONTEND_URL" ]; then
  cd "$REPO_ROOT/backend"
  echo "  Updating CORS origins to: $FRONTEND_URL"
  railway variables set ALLOWED_ORIGINS="$FRONTEND_URL" 2>/dev/null || true
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  DEPLOYMENT COMPLETE"
echo "======================================"
echo ""
[ -n "$BACKEND_URL" ]  && echo "  Backend:  $BACKEND_URL"
[ -n "$FRONTEND_URL" ] && echo "  Frontend: $FRONTEND_URL"
echo ""
echo "  API docs: $BACKEND_URL/docs"
echo ""
echo "  Add these as additional Railway services for background jobs:"
echo "  Worker: celery -A worker.celery_app worker --loglevel=info --concurrency=2"
echo "  Beat:   celery -A worker.celery_app beat --loglevel=info --scheduler redbeat.RedBeatScheduler"
echo ""
