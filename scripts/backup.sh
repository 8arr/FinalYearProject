#!/bin/bash
# Makes a consistent copy of the database and uploads it to OneDrive with rclone.
# Run from cron, see docs/gcp-setup.md
set -e

cd "$(dirname "$0")/.."
stamp=$(date -u +%Y%m%d-%H%M)
out="/tmp/bus-$stamp.db"

sqlite3 data/bus.db ".backup '$out'"
gzip "$out"
rclone copy "$out.gz" onedrive:fyp-backups
rm "$out.gz"

# keep the last 30 days on OneDrive
rclone delete onedrive:fyp-backups --min-age 30d
