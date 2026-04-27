#!/bin/bash

# Wait for database to be ready
echo "Waiting for database..."
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

# Try to wait for database if nc is available, otherwise just wait a bit
if command -v nc >/dev/null 2>&1; then
  while ! nc -z $DB_HOST $DB_PORT; do
    echo "Database not ready, waiting..."
    sleep 1
  done
else
  echo "nc not found, sleeping for 5s to allow DB startup..."
  sleep 5
fi

echo "Database is ready!"

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Start the server
echo "Starting Django server..."
exec python manage.py runserver 0.0.0.0:8000