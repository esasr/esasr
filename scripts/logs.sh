#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ $# -gt 0 ]]; then
  docker compose logs --tail=200 --follow "$@"
else
  docker compose logs --tail=200 --follow
fi
