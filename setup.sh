#!/bin/bash
set -euo pipefail

# =============================================================
# LiteLLM + CommandCode VPS Deployment Script
# =============================================================
# Usage: chmod +x setup.sh && ./setup.sh
#
# Prerequisites: git, docker, docker compose plugin

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Check prerequisites ---
command -v git >/dev/null 2>&1 || die "git is not installed"
command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "docker compose plugin is not installed"

# --- Ask for COMMANDCODE_API_KEY if not set ---
if [ -z "${COMMANDCODE_API_KEY:-}" ]; then
    read -r -p "Enter your CommandCode API key: " COMMANDCODE_API_KEY
    if [ -z "$COMMANDCODE_API_KEY" ]; then
        die "COMMANDCODE_API_KEY is required"
    fi
fi

# --- Ask for proxy port ---
read -r -p "Proxy port [4000]: " PROXY_PORT
PROXY_PORT=${PROXY_PORT:-4000}

# --- Clone repo if not already in one ---
REPO_URL="https://github.com/tuyenbui3030/litellm.git"
BRANCH="tuyenbui3030/add-commandcode-provider"
PROJECT_DIR="litellm-deploy"

if [ -d "$PROJECT_DIR/.git" ]; then
    log "Stopping existing containers..."
    (cd "$PROJECT_DIR" && docker compose down --remove-orphans 2>/dev/null || true)

    log "Project directory exists, resetting and pulling latest..."
    (cd "$PROJECT_DIR" && git fetch origin "$BRANCH" && git checkout -f "$BRANCH" && git reset --hard "origin/$BRANCH")
else
    log "Cloning repo..."
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# --- Clean up any leftover containers from previous runs ---
log "Cleaning up old containers..."
docker compose down --remove-orphans 2>/dev/null || true
# Remove any container with 'litellm' in the name that might be from old runs
for cid in $(docker ps -aq --filter "name=litellm" 2>/dev/null); do
    docker rm -f "$cid" 2>/dev/null || true
done

# --- Check for existing master key in .env or generate new one ---
EXISTING_KEY=""
if [ -f "$PROJECT_DIR/.env" ]; then
    EXISTING_KEY=$(grep "^LITELLM_MASTER_KEY=" "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2-)
fi

if [ -n "$EXISTING_KEY" ]; then
    MASTER_KEY="$EXISTING_KEY"
    log "Reusing existing master key from .env"
else
    MASTER_KEY="sk-$(openssl rand -hex 32)"
    log "Generated new master key"
fi

# --- Create .env file ---
cat > .env <<EOF
COMMANDCODE_API_KEY=${COMMANDCODE_API_KEY}
LITELLM_MASTER_KEY=${MASTER_KEY}
UI_USERNAME=admin
EOF
log "Created .env file"

# --- Adjust port in docker-compose.yml ---
if [ "$PROXY_PORT" != "4000" ]; then
    sed -i "s/-\"4000:4000\"/-\"${PROXY_PORT}:4000\"/" docker-compose.yml
    log "Proxy port set to ${PROXY_PORT}"
fi

# --- Build & start ---
log "Building Docker image (this may take a few minutes)..."
docker compose build litellm

log "Starting services..."
docker compose up -d

# --- Wait for healthy ---
log "Waiting for proxy to be ready..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:"$PROXY_PORT"/health/liveliness >/dev/null 2>&1; then
        echo ""
        echo "============================================"
        log "LiteLLM proxy is running!"
        echo "============================================"
        echo ""
        echo "  Dashboard:        http://localhost:${PROXY_PORT}/ui/"
        echo "  API Base:         http://localhost:${PROXY_PORT}"
        echo "  UI Username:      admin"
        echo "  Master Key:       ${MASTER_KEY}"
        echo ""
        echo "============================================"
        echo ""
        exit 0
    fi
    sleep 2
done

warn "Proxy may still be starting. Check logs: docker compose logs -f litellm"
