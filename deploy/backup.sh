#!/bin/sh
# Nightly logical backup; optionally copied off-box with rclone.
set -eu
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=/backups/attool-${STAMP}.dump
pg_dump "${DATABASE_URL}" -Fc -f "${OUT}"
echo "backup written: ${OUT} ($(du -h "${OUT}" | cut -f1))"
find /backups -name 'attool-*.dump' -mtime "+${BACKUP_RETENTION_DAYS:-30}" -delete
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  if command -v rclone >/dev/null 2>&1; then
    rclone copy "${OUT}" "${BACKUP_RCLONE_REMOTE}/"
    echo "backup copied to ${BACKUP_RCLONE_REMOTE}"
  else
    echo "BACKUP_RCLONE_REMOTE set but rclone is not installed in the image" >&2
  fi
fi
