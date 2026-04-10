#!/bin/bash
# ============================================================
# FamOS Cloud Backup Script (using rclone)
# Supports: Google Drive, Backblaze B2, S3, Dropbox, and more
#
# Setup: run `rclone config` once to connect your cloud storage
# Then set RCLONE_REMOTE below to your remote name + path
# ============================================================

set -euo pipefail

# ---- CONFIG ------------------------------------------------
DATA_DIR="/opt/famos/backend"        # Where your app lives
BACKUP_DIR="/opt/famos/backups"      # Local staging for backup archives
RCLONE_REMOTE="gdrive:FamOS-Backups" # Change to your rclone remote:path
KEEP_LOCAL_DAYS=7                    # Days of local backups to keep
KEEP_CLOUD_DAYS=30                   # Days of cloud backups to keep
LOG_FILE="/opt/famos/backend/logs/backup.log"
# ------------------------------------------------------------

TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_NAME="famos_backup_${TIMESTAMP}"
STAGING="${BACKUP_DIR}/${BACKUP_NAME}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "========== FamOS Backup Started =========="

# 1. Create local staging directory
mkdir -p "$STAGING"

# 2. Backup SQLite database (atomic copy using SQLite's backup API)
log "Backing up SQLite database..."
if [ -f "${DATA_DIR}/db/app.db" ]; then
    sqlite3 "${DATA_DIR}/db/app.db" ".backup '${STAGING}/app.db'"
    log "  ✓ Database backed up ($(du -sh ${STAGING}/app.db | cut -f1))"
else
    log "  ⚠ Database file not found at ${DATA_DIR}/db/app.db"
fi

# 3. Backup uploaded documents
log "Backing up uploaded documents..."
if [ -d "${DATA_DIR}/uploads" ]; then
    cp -r "${DATA_DIR}/uploads" "${STAGING}/secure_uploads"
    log "  ✓ Documents backed up ($(du -sh ${STAGING}/secure_uploads | cut -f1))"
else
    log "  ⚠ Uploads directory not found"
fi

# 4. Backup .env file (contains encryption keys — critical!)
log "Backing up environment secrets..."
if [ -f "/opt/famos/backend/.env" ]; then
    cp "/opt/famos/backend/.env" "${STAGING}/.env"
    chmod 600 "${STAGING}/.env"
    log "  ✓ Secrets backed up"
fi

# 5. Create compressed archive
log "Compressing backup..."
ARCHIVE="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
tar -czf "$ARCHIVE" -C "$BACKUP_DIR" "$BACKUP_NAME"
ARCHIVE_SIZE=$(du -sh "$ARCHIVE" | cut -f1)
log "  ✓ Archive created: ${ARCHIVE} (${ARCHIVE_SIZE})"

# Remove staging directory (keep only the archive locally)
rm -rf "$STAGING"

# 6. Upload to cloud via rclone
log "Uploading to cloud (${RCLONE_REMOTE})..."
if command -v rclone &>/dev/null; then
    rclone copy "$ARCHIVE" "${RCLONE_REMOTE}/" \
        --log-file="$LOG_FILE" \
        --log-level INFO \
        --retries 3 \
        --low-level-retries 5 \
        --stats 60s
    log "  ✓ Uploaded to cloud successfully"

    # 7. Delete old cloud backups
    log "Pruning cloud backups older than ${KEEP_CLOUD_DAYS} days..."
    rclone delete "${RCLONE_REMOTE}/" \
        --min-age "${KEEP_CLOUD_DAYS}d" \
        --log-file="$LOG_FILE" \
        --log-level INFO
    log "  ✓ Cloud pruning done"
else
    log "  ⚠ rclone not found — skipping cloud upload"
    log "    Install: curl https://rclone.org/install.sh | sudo bash"
fi

# 8. Delete old local backups
log "Pruning local backups older than ${KEEP_LOCAL_DAYS} days..."
find "$BACKUP_DIR" -name "famos_backup_*.tar.gz" -mtime "+${KEEP_LOCAL_DAYS}" -delete
log "  ✓ Local pruning done"

# 9. Summary
log "========== Backup Complete =========="
log "  Archive : $ARCHIVE (${ARCHIVE_SIZE})"
log "  Cloud   : ${RCLONE_REMOTE}/${BACKUP_NAME}.tar.gz"
log "  Local   : Keeping last ${KEEP_LOCAL_DAYS} days"
log "  Cloud   : Keeping last ${KEEP_CLOUD_DAYS} days"
