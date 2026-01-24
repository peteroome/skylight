#!/bin/bash
# dev.sh - Run Skylight locally for development

set -e

echo "🛫 Starting Skylight development server..."

# Kill any existing processes on exit
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $PYTHON_PID 2>/dev/null || true
  kill $SERVER_PID 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# Start flight data fetcher in background
echo "Starting flight data service..."
python3 fetch_flights.py &
PYTHON_PID=$!

# Give it a moment to create initial files
sleep 2

# Start HTTP server
echo "Starting HTTP server on http://localhost:8000"
cd web
python3 -m http.server 8000 &
SERVER_PID=$!
cd ..

echo ""
echo "✅ Skylight running!"
echo "   Open http://localhost:8000 in your browser"
echo "   Press Ctrl+C to stop"
echo ""

# Wait for either process to exit
wait
