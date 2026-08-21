#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BUILD=true
PULL=false
WITH_RERANKER=false

for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=false ;;
    --pull) PULL=true ;;
    --with-reranker) WITH_RERANKER=true ;;
    -h|--help)
      echo "Usage: ./scripts/start.sh [--no-build] [--pull] [--with-reranker]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or is not on PATH." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

compose() {
  if [[ -n "${SCHOLARSEEKER_COMPOSE_PROGRESS:-}" ]]; then
    COMPOSE_BAKE="${COMPOSE_BAKE:-true}" docker compose --progress "$SCHOLARSEEKER_COMPOSE_PROGRESS" "$@"
  else
    docker compose "$@"
  fi
}

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "The project can start without an LLM key, but query planning will use its heuristic fallback."
fi

if [[ ! -f config.yaml ]]; then
  cp config_example.yaml config.yaml
  echo "Created config.yaml from config_example.yaml. Runtime secrets remain in .env."
fi

if [[ "$WITH_RERANKER" == true ]]; then
  export INSTALL_RERANKER=true
  export CROSS_ENCODER_ENABLED=true
  echo "Cross Encoder image dependencies enabled; the first build and model download will take longer."
fi

if [[ "$PULL" == true ]]; then
  compose pull
fi

if [[ "$BUILD" == true ]]; then
  if ! compose up -d --build; then
    echo
    echo "Compose failed to start all services. Current status:" >&2
    compose ps -a
    if compose logs --no-color --tail=160 api postgres 2>/dev/null \
      | grep -q "password authentication failed"; then
      echo >&2
      echo "PostgreSQL credentials do not match the existing persistent volume." >&2
      echo "If the old data is disposable, run: ./scripts/stop.sh --volumes" >&2
      echo "Otherwise restore the password originally used to create the volume in .env." >&2
    fi
    exit 1
  fi
else
  if ! compose up -d; then
    echo
    compose ps -a
    compose logs --no-color --tail=120 api
    exit 1
  fi
fi

WEB_PORT_VALUE="${WEB_PORT:-$(sed -n 's/^WEB_PORT=//p' .env | tail -n 1)}"
API_PORT_VALUE="${API_PORT:-$(sed -n 's/^API_PORT=//p' .env | tail -n 1)}"
WEB_PORT_VALUE="${WEB_PORT_VALUE:-8080}"
API_PORT_VALUE="${API_PORT_VALUE:-8000}"

echo "Waiting for ScholarSeeker services..."
deadline=$((SECONDS + ${START_TIMEOUT:-180}))
while (( SECONDS < deadline )); do
  if curl -fsS "http://127.0.0.1:${API_PORT_VALUE}/health" >/dev/null 2>&1 \
    && curl -fsS "http://127.0.0.1:${WEB_PORT_VALUE}/health" >/dev/null 2>&1; then
    echo
    echo "ScholarSeeker is ready."
    echo "Web:       http://127.0.0.1:${WEB_PORT_VALUE}"
    echo "API docs:  http://127.0.0.1:${API_PORT_VALUE}/docs"
    echo "Neo4j:     http://127.0.0.1:${NEO4J_HTTP_PORT:-7474}"
    echo
    echo "Logs: ./scripts/logs.sh"
    echo "Stop: ./scripts/stop.sh"
    exit 0
  fi
  sleep 2
done

echo "Timed out waiting for services." >&2
compose ps
echo
compose logs --tail=80 api web
exit 1
