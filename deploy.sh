#!/bin/bash
# ============================================================
# FamOS Auto-Deploy Script
# Called by the GitHub webhook on every push to main branch.
# Run manually anytime: bash ~/famos/deploy.sh
# ============================================================

set -euo pipefail

APP_DIR="$HOME/famos/backend"
LOG="$APP_DIR/logs/deploy.log"
BRANCH="main"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "===== Deploy triggered ====="

# 1. Pull latest code
log "Pulling latest code from origin/$BRANCH..."
cd "$APP_DIR/.."
git fetch origin
git reset --hard origin/$BRANCH
log "  ✓ Code updated to $(git rev-parse --short HEAD)"

# 2. Install any new Python dependencies
log "Installing dependencies..."
cd "$APP_DIR"
source venv/bin/activate
pip install -q -r requirements.txt
log "  ✓ Dependencies ready"

# 3. Run database migrations (safe to run multiple times)
log "Running migrations..."
python migrate.py >> "$LOG" 2>&1
log "  ✓ Migrations done"

# 4. Restart the service
log "Restarting famos service..."
sudo systemctl restart famos
sleep 2

# 5. Health check
if curl -sf http://localhost:5000/health > /dev/null; then
    log "  ✓ Health check passed — deploy successful"
else
    log "  ✗ Health check FAILED — check logs"
    sudo journalctl -u famos -n 20 >> "$LOG" 2>&1
    exit 1
fi

log "===== Deploy complete ====="
