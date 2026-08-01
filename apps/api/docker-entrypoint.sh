#!/bin/sh
# Named volumes keep whatever ownership they had on first creation, which can
# predate appuser or drift after a volume is reused across image rebuilds.
# Re-chown on every start (root, pre-exec) so the mount always matches the
# image's build-time ownership before appuser touches it.
set -e
mkdir -p /app/config /app/.cache
chown -R appuser:appuser /app/data/uploads /app/.cache /app/config
exec gosu appuser "$@"
