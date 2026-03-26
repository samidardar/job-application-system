#!/bin/bash
set -e

echo "▶ Running Alembic migrations..."
alembic upgrade head

echo "▶ Starting Postulio API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
