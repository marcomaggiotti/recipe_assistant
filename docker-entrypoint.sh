#!/bin/sh
set -e

case "${SERVICE:-pizza-service}" in
  pizza-service)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  topping-service)
    exec uvicorn topping_service.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  *)
    echo "Unknown SERVICE '${SERVICE}' - expected 'pizza-service' or 'topping-service'" >&2
    exit 1
    ;;
esac
